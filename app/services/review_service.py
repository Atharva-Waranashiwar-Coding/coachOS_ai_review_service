"""Business rules for asynchronous, coach-owned AI reviews."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, UpstreamServiceError
from app.models.review import AIReview, JobStatus, ReviewGenerationJob, ReviewRevision, ReviewStatus
from app.schemas.review import DraftUpdate, ReviewCreate
from app.services.timeline_events import ai_timeline_event


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _context_snapshot(self, payload: ReviewCreate, bearer_token: str) -> dict[str, object]:
        """Fetch and retain only metadata that can safely inform a textual review."""
        headers = {"Authorization": f"Bearer {bearer_token}"}
        try:
            with httpx.Client(timeout=settings.upstream_timeout_seconds) as client:
                athlete = client.get(
                    f"{settings.athlete_service_url.rstrip('/')}/api/v1/athletes/{payload.athlete_id}", headers=headers
                )
                video = client.get(
                    f"{settings.media_service_url.rstrip('/')}/api/v1/videos/{payload.video_id}", headers=headers
                )
                practice_session = client.get(
                    f"{settings.media_service_url.rstrip('/')}/api/v1/practice-sessions/{payload.practice_session_id}",
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError("Required context service is unavailable.") from exc

        if any(response.status_code != 200 for response in (athlete, video, practice_session)):
            raise NotFoundError("Athlete, video, or practice session was not found.")

        athlete_data, video_data, session_data = athlete.json(), video.json(), practice_session.json()
        if (
            video_data.get("athlete_id") != str(payload.athlete_id)
            or video_data.get("practice_session_id") != str(payload.practice_session_id)
            or session_data.get("athlete_id") != str(payload.athlete_id)
            or video_data.get("upload_status") != "uploaded"
        ):
            raise BadRequestError("The selected uploaded video does not belong to this athlete and session.")

        return {
            "athlete": {
                key: athlete_data.get(key)
                for key in (
                    "id",
                    "first_name",
                    "last_name",
                    "preferred_name",
                    "primary_position",
                    "secondary_positions",
                    "bats",
                    "throws",
                    "graduation_year",
                    "team_name",
                    "school_name",
                )
            },
            "practice_session": {
                key: session_data.get(key)
                for key in ("id", "title", "description", "session_type", "session_date", "location")
            },
            "video": {
                key: video_data.get(key)
                for key in (
                    "id",
                    "original_filename",
                    "content_type",
                    "duration_seconds",
                    "width",
                    "height",
                    "frame_rate",
                )
            },
        }

    @staticmethod
    def _fingerprint(payload: ReviewCreate) -> str:
        return hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

    def create(self, payload: ReviewCreate, user_id: UUID, bearer_token: str, idempotency_key: str | None) -> AIReview:
        if len(payload.coach_context or "") > settings.max_coach_context_characters:
            raise BadRequestError("Coach context exceeds the configured limit.")
        if len(payload.transcript or "") > settings.max_transcript_characters:
            raise BadRequestError("Transcript exceeds the configured limit.")
        if len(payload.manual_observations) > settings.max_manual_observations:
            raise BadRequestError("Too many manual observations.")
        if len(payload.frame_observations) > settings.max_frame_observations:
            raise BadRequestError("Too many frame observations.")

        fingerprint = self._fingerprint(payload)
        if idempotency_key:
            existing = self.db.scalar(
                select(AIReview).where(
                    AIReview.requested_by_user_id == user_id,
                    AIReview.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.request_fingerprint != fingerprint:
                    raise ConflictError("Idempotency key was used with a different request.")
                return existing

        review = AIReview(
            **payload.model_dump(),
            context_snapshot=self._context_snapshot(payload, bearer_token),
            requested_by_user_id=user_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            prompt_version=settings.prompt_version,
            schema_version=settings.review_schema_version,
        )
        self.db.add(review)
        self.db.flush()
        self.db.add(ReviewGenerationJob(review_id=review.id))
        self.db.add(
            ai_timeline_event(
                event_type="ai_review_requested",
                athlete_id=review.athlete_id,
                review_id=review.id,
                actor_user_id=user_id,
                occurred_at=datetime.now(UTC),
                metadata={
                    "review_id": str(review.id),
                    "video_id": str(review.video_id),
                    "practice_session_id": str(review.practice_session_id),
                },
            )
        )
        self.db.commit()
        self.db.refresh(review)
        return review

    def get(self, review_id: UUID, user_id: UUID) -> AIReview:
        review = self.db.scalar(
            select(AIReview).where(AIReview.id == review_id, AIReview.requested_by_user_id == user_id)
        )
        if not review:
            raise NotFoundError("Review not found.")
        return review

    def list(
        self,
        user_id: UUID,
        athlete_id: UUID | None = None,
        video_id: UUID | None = None,
        status: ReviewStatus | None = None,
    ) -> list[AIReview]:
        statement = select(AIReview).where(AIReview.requested_by_user_id == user_id)
        if athlete_id:
            statement = statement.where(AIReview.athlete_id == athlete_id)
        if video_id:
            statement = statement.where(AIReview.video_id == video_id)
        if status:
            statement = statement.where(AIReview.status == status)
        return list(self.db.scalars(statement.order_by(AIReview.created_at.desc())))

    def revise(self, review: AIReview, payload: DraftUpdate, user_id: UUID) -> ReviewRevision:
        if review.status not in {ReviewStatus.GENERATED, ReviewStatus.APPROVED}:
            raise BadRequestError("Only generated reviews can be edited.")
        revision_number = (
            self.db.scalar(
                select(func.max(ReviewRevision.revision_number)).where(ReviewRevision.review_id == review.id)
            )
            or 0
        ) + 1
        revision = ReviewRevision(
            review_id=review.id, revision_number=revision_number, edited_by_user_id=user_id, **payload.model_dump()
        )
        self.db.add(revision)
        self.db.add(
            ai_timeline_event(
                event_type="coach_review_edited",
                athlete_id=review.athlete_id,
                review_id=review.id,
                actor_user_id=user_id,
                occurred_at=datetime.now(UTC),
                metadata={"review_id": str(review.id), "video_id": str(review.video_id)},
            )
        )
        self.db.commit()
        self.db.refresh(revision)
        return revision

    def approve(self, review: AIReview, user_id: UUID) -> AIReview:
        if review.status == ReviewStatus.APPROVED:
            return review
        if review.status != ReviewStatus.GENERATED:
            raise BadRequestError("Review is not ready for approval.")
        review.status = ReviewStatus.APPROVED
        review.approved_at = datetime.now(UTC)
        self.db.add(
            ai_timeline_event(
                event_type="coach_review_approved",
                athlete_id=review.athlete_id,
                review_id=review.id,
                actor_user_id=user_id,
                occurred_at=review.approved_at,
                metadata={
                    "review_id": str(review.id),
                    "video_id": str(review.video_id),
                    "practice_session_id": str(review.practice_session_id),
                },
            )
        )
        self.db.commit()
        return review

    def reject(self, review: AIReview, user_id: UUID, reason: str | None) -> AIReview:
        if review.status == ReviewStatus.REJECTED:
            return review
        if review.status not in {ReviewStatus.GENERATED, ReviewStatus.APPROVED}:
            raise BadRequestError("Review is not ready for rejection.")
        review.status, review.rejected_at, review.rejection_reason = ReviewStatus.REJECTED, datetime.now(UTC), reason
        self.db.add(
            ai_timeline_event(
                event_type="coach_review_rejected",
                athlete_id=review.athlete_id,
                review_id=review.id,
                actor_user_id=user_id,
                occurred_at=review.rejected_at,
                metadata={"review_id": str(review.id), "video_id": str(review.video_id)},
            )
        )
        self.db.commit()
        return review

    def retry(self, review: AIReview) -> AIReview:
        if review.status != ReviewStatus.FAILED:
            raise BadRequestError("Only failed reviews can be retried.")
        job = self.db.scalar(select(ReviewGenerationJob).where(ReviewGenerationJob.review_id == review.id))
        if not job:
            raise NotFoundError("Review generation job not found.")
        review.status, review.failure_reason = ReviewStatus.PENDING, None
        job.status, job.available_at, job.last_error = JobStatus.PENDING, datetime.now(UTC), None
        self.db.commit()
        return review

    def cancel(self, review: AIReview) -> AIReview:
        if review.status not in {ReviewStatus.PENDING, ReviewStatus.PROCESSING}:
            return review
        review.status = ReviewStatus.CANCELLED
        job = self.db.scalar(select(ReviewGenerationJob).where(ReviewGenerationJob.review_id == review.id))
        if job:
            job.status = JobStatus.CANCELLED
        self.db.commit()
        return review
