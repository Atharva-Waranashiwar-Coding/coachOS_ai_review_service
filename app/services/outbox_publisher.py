from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbox import OutboxEvent, OutboxStatus


class OutboxPublisher:
    def __init__(self, db: Session, client: httpx.Client | None = None):
        self.db, self.client = db, client or httpx.Client(timeout=settings.upstream_timeout_seconds)

    def claim(self) -> list[OutboxEvent]:
        events = list(
            self.db.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == OutboxStatus.PENDING,
                    OutboxEvent.available_at <= datetime.now(UTC),
                )
                .order_by(OutboxEvent.created_at)
                .limit(settings.outbox_batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for event in events:
            event.status = OutboxStatus.PROCESSING
        self.db.commit()
        return events

    def publish_batch(self) -> int:
        success = 0
        for event in self.claim():
            try:
                r = self.client.post(
                    f"{settings.athlete_service_internal_url.rstrip('/')}/internal/v1/athletes/{event.payload['athlete_id']}/timeline-events",
                    json=event.payload,
                    headers={
                        "X-Service-Name": settings.internal_service_name,
                        "X-Service-Token": settings.internal_service_token,
                        "X-Request-ID": str(event.id),
                    },
                )
                if r.status_code in {200, 201}:
                    event.status, event.published_at, event.last_error = (
                        OutboxStatus.PUBLISHED,
                        datetime.now(UTC),
                        None,
                    )
                    success += 1
                else:
                    self._fail(
                        event,
                        f"HTTP {r.status_code}",
                        r.status_code in {400, 401, 403, 409, 422},
                    )
            except httpx.HTTPError as exc:
                self._fail(event, type(exc).__name__)
            self.db.commit()
        return success

    def _fail(self, event: OutboxEvent, message: str, permanent: bool = False) -> None:
        event.attempt_count += 1
        event.last_error = message[:500]
        event.status = (
            OutboxStatus.FAILED
            if permanent or event.attempt_count >= settings.outbox_max_attempts
            else OutboxStatus.PENDING
        )
        event.available_at = datetime.now(UTC) + timedelta(
            seconds=min(
                settings.outbox_base_retry_seconds * 2 ** max(event.attempt_count - 1, 0),
                3600,
            )
        )
