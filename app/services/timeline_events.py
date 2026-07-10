from datetime import datetime
from uuid import UUID, uuid4

from app.models.outbox import OutboxEvent

AI_EVENTS = {
    "ai_review_requested": ("ai_review", "coach_only", "AI review requested"),
    "ai_review_generated": ("ai_review", "coach_only", "AI review generated"),
    "ai_review_failed": ("ai_review", "coach_only", "AI review failed"),
    "coach_review_edited": ("coach_review", "coach_only", "Coach feedback edited"),
    "coach_review_approved": (
        "coach_review",
        "athlete_visible",
        "Coach feedback approved",
    ),
    "coach_review_rejected": ("coach_review", "coach_only", "Coach feedback rejected"),
}
SAFE_METADATA = {"review_id", "practice_session_id", "video_id"}


def ai_timeline_event(
    *,
    event_type: str,
    athlete_id: UUID,
    review_id: UUID,
    actor_user_id: UUID | None,
    occurred_at: datetime,
    metadata: dict[str, object] | None = None,
    description: str | None = None,
) -> OutboxEvent:
    if event_type not in AI_EVENTS:
        raise ValueError("Unsupported AI timeline event")
    if metadata and set(metadata) - SAFE_METADATA:
        raise ValueError("Timeline metadata contains unsafe keys")
    category, visibility, title = AI_EVENTS[event_type]
    event_id = uuid4()
    payload = {
        "event_id": str(event_id),
        "athlete_id": str(athlete_id),
        "event_type": event_type,
        "event_category": category,
        "title": title,
        "description": description,
        "source_service": "ai-review-service",
        "source_entity_type": "ai_review",
        "source_entity_id": str(review_id),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "occurred_at": occurred_at.isoformat(),
        "metadata": metadata or {},
        "schema_version": 1,
        "visibility": visibility,
    }
    return OutboxEvent(
        aggregate_type="ai_review",
        aggregate_id=str(review_id),
        event_type=event_type,
        payload=payload,
    )
