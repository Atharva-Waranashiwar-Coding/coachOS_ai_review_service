"""Domain services for asynchronous generation and human coach review workflow."""

import builtins
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    StaleReviewRevisionError,
    UpstreamServiceError,
)
from app.models.review import (
    AIReview,
    ApprovedReviewSnapshot,
    AuditAction,
    JobStatus,
    ReviewAuditEvent,
    ReviewGenerationJob,
    ReviewRejection,
    ReviewRevision,
    ReviewStatus,
)
from app.schemas.review import (
    ActiveDraft,
    ApprovalRequest,
    AthletePreview,
    PreviewRequest,
    RejectionRequest,
    ReviewCreate,
    ReviewRevisionCreate,
)
from app.services.timeline_events import ai_timeline_event


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _context_snapshot(self, payload: ReviewCreate, bearer_token: str) -> dict[str, object]:
        """Capture only authorized, text-safe source-service metadata for generation."""
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

    @staticmethod
    def _audit(
        review_id: UUID, action: AuditAction, actor_user_id: UUID | None, metadata: dict[str, object] | None = None
    ) -> ReviewAuditEvent:
        return ReviewAuditEvent(
            review_id=review_id,
            actor_user_id=actor_user_id,
            action_type=action,
            metadata_json=metadata or {},
            occurred_at=datetime.now(UTC),
        )

    def create(self, payload: ReviewCreate, user_id: UUID, bearer_token: str, idempotency_key: str | None) -> AIReview:
        if len(payload.coach_context or "") > settings.max_coach_context_characters:
            raise BadRequestError("Coach context exceeds the configured limit.")
        if len(payload.transcript or "") > settings.max_transcript_characters:
            raise BadRequestError("Transcript exceeds the configured limit.")
        if (
            len(payload.manual_observations) > settings.max_manual_observations
            or len(payload.frame_observations) > settings.max_frame_observations
        ):
            raise BadRequestError("Review context exceeds the configured limit.")
        fingerprint = self._fingerprint(payload)
        if idempotency_key:
            existing = self.db.scalar(
                select(AIReview).where(
                    AIReview.requested_by_user_id == user_id, AIReview.idempotency_key == idempotency_key
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
                    "review_type": review.review_type.value,
                },
            )
        )
        self.db.commit()
        self.db.refresh(review)
        return review

    def get(self, review_id: UUID, user_id: UUID, *, lock: bool = False) -> AIReview:
        statement = select(AIReview).where(AIReview.id == review_id, AIReview.requested_by_user_id == user_id)
        if lock:
            statement = statement.with_for_update()
        review = self.db.scalar(statement)
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

    def get_active_draft(self, review: AIReview) -> ActiveDraft:
        """Resolve the editable source without ever using an approved snapshot."""
        revision = self.db.scalar(
            select(ReviewRevision)
            .where(ReviewRevision.review_id == review.id)
            .order_by(ReviewRevision.revision_number.desc())
        )
        if revision:
            return ActiveDraft.model_validate(
                {
                    "source": "revision",
                    "revision_id": revision.id,
                    "revision_number": revision.revision_number,
                    "summary": revision.summary,
                    "observations": revision.observations,
                    "strengths": revision.strengths,
                    "improvement_areas": revision.improvement_areas,
                    "recommended_drills": revision.recommended_drills,
                    "coach_notes": revision.coach_notes,
                    "athlete_message": revision.athlete_message,
                    "change_summary": revision.change_summary,
                }
            )
        if not review.result:
            raise BadRequestError("Generated review content is not available.")
        result = review.result
        return ActiveDraft.model_validate(
            {
                "source": "generated",
                "revision_id": None,
                "revision_number": 0,
                "summary": result.summary,
                "observations": result.observations,
                "strengths": result.strengths,
                "improvement_areas": result.improvement_areas,
                "recommended_drills": result.recommended_drills,
                "coach_notes": None,
                "athlete_message": None,
            }
        )

    def _revision_for_id(self, review: AIReview, revision_id: UUID) -> ReviewRevision:
        revision = self.db.scalar(
            select(ReviewRevision).where(ReviewRevision.id == revision_id, ReviewRevision.review_id == review.id)
        )
        if not revision:
            raise NotFoundError("Review revision not found.")
        return revision

    def create_revision(self, review_id: UUID, user_id: UUID, payload: ReviewRevisionCreate) -> ReviewRevision:
        review = self.get(review_id, user_id, lock=True)
        if review.status != ReviewStatus.GENERATED:
            raise BadRequestError("Only generated reviews can be edited.")
        if payload.expected_revision_number != review.latest_revision_number:
            raise StaleReviewRevisionError(review.latest_revision_number)
        revision = ReviewRevision(
            review_id=review.id,
            revision_number=review.latest_revision_number + 1,
            edited_by_user_id=user_id,
            based_on_revision_number=review.latest_revision_number or None,
            **payload.model_dump(exclude={"expected_revision_number"}),
        )
        review.latest_revision_number = revision.revision_number
        self.db.add_all(
            [
                revision,
                self._audit(
                    review.id,
                    AuditAction.REVISION_CREATED,
                    user_id,
                    {"revision_number": revision.revision_number, "changed_sections": self._changed_sections(payload)},
                ),
            ]
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise StaleReviewRevisionError(review.latest_revision_number) from exc
        self.db.refresh(revision)
        return revision

    @staticmethod
    def _changed_sections(payload: ReviewRevisionCreate) -> builtins.list[str]:
        return [
            name
            for name, value in payload.model_dump(exclude={"expected_revision_number"}).items()
            if value not in (None, [], "")
        ]

    def list_revisions(self, review: AIReview, page: int, page_size: int) -> tuple[builtins.list[ReviewRevision], int]:
        statement = (
            select(ReviewRevision)
            .where(ReviewRevision.review_id == review.id)
            .order_by(ReviewRevision.revision_number.desc())
        )
        total = len(list(self.db.scalars(statement)))
        return list(self.db.scalars(statement.offset((page - 1) * page_size).limit(page_size))), total

    def preview(self, review_id: UUID, user_id: UUID, payload: PreviewRequest) -> AthletePreview:
        review = self.get(review_id, user_id)
        if review.status not in {ReviewStatus.GENERATED, ReviewStatus.APPROVED}:
            raise BadRequestError("Review is not ready for preview.")
        draft = (
            self.get_active_draft(review)
            if not payload.revision_id
            else self._draft_from_revision(self._revision_for_id(review, payload.revision_id))
        )
        self.db.add(
            self._audit(
                review.id,
                AuditAction.PREVIEW_REQUESTED,
                user_id,
                {"revision_number": draft.revision_number, "visibility": payload.visibility.value},
            )
        )
        self.db.commit()
        observations = [
            {
                "title": item.title,
                "description": item.description,
                "category": item.category,
                "priority": item.priority,
                "coach_verified": item.coach_verified,
            }
            for item in draft.observations
        ]
        return AthletePreview(
            athlete_id=review.athlete_id,
            review_id=review.id,
            summary=draft.summary,
            observations=observations,
            strengths=draft.strengths,
            improvement_areas=draft.improvement_areas,
            recommended_drills=draft.recommended_drills,
            athlete_message=payload.athlete_message if payload.athlete_message is not None else draft.athlete_message,
            visibility=payload.visibility,
        )

    @staticmethod
    def _draft_from_revision(revision: ReviewRevision) -> ActiveDraft:
        return ActiveDraft.model_validate(
            {
                "source": "revision",
                "revision_id": revision.id,
                "revision_number": revision.revision_number,
                "summary": revision.summary,
                "observations": revision.observations,
                "strengths": revision.strengths,
                "improvement_areas": revision.improvement_areas,
                "recommended_drills": revision.recommended_drills,
                "coach_notes": revision.coach_notes,
                "athlete_message": revision.athlete_message,
                "change_summary": revision.change_summary,
            }
        )

    def approve(self, review_id: UUID, user_id: UUID, payload: ApprovalRequest) -> ApprovedReviewSnapshot:
        if not payload.confirmation:
            raise BadRequestError("Approval confirmation is required.")
        review = self.get(review_id, user_id, lock=True)
        if review.status == ReviewStatus.APPROVED:
            snapshot = review.approved_snapshot
            active_message = self.get_active_draft(review).athlete_message if review.result else None
            candidate_message = payload.athlete_message if payload.athlete_message is not None else active_message
            if snapshot and snapshot.visibility == payload.visibility and snapshot.athlete_message == candidate_message:
                return snapshot
            raise ConflictError("Review has already been approved with different content or visibility.")
        if review.status != ReviewStatus.GENERATED:
            raise BadRequestError("Review is not ready for approval.")
        if payload.expected_revision_number != review.latest_revision_number:
            raise StaleReviewRevisionError(review.latest_revision_number)
        draft = self.get_active_draft(review)
        if payload.revision_id and payload.revision_id != draft.revision_id:
            raise ConflictError("Only the latest review revision can be approved.")
        approved_at = datetime.now(UTC)
        snapshot = ApprovedReviewSnapshot(
            review_id=review.id,
            source_revision_id=draft.revision_id,
            approved_by_user_id=user_id,
            summary=draft.summary,
            observations=[item.model_dump(mode="json") for item in draft.observations],
            strengths=[item.model_dump(mode="json") for item in draft.strengths],
            improvement_areas=[item.model_dump(mode="json") for item in draft.improvement_areas],
            recommended_drills=[item.model_dump(mode="json") for item in draft.recommended_drills],
            athlete_message=payload.athlete_message if payload.athlete_message is not None else draft.athlete_message,
            visibility=payload.visibility,
            approved_at=approved_at,
        )
        self.db.add(snapshot)
        self.db.flush()
        review.status, review.approved_at, review.approved_snapshot_id = ReviewStatus.APPROVED, approved_at, snapshot.id
        safe_metadata: dict[str, object] = {
            "review_id": str(review.id),
            "video_id": str(review.video_id),
            "practice_session_id": str(review.practice_session_id),
            "review_type": review.review_type.value,
            "visibility": payload.visibility.value,
        }
        self.db.add_all(
            [
                self._audit(
                    review.id,
                    AuditAction.REVIEW_APPROVED,
                    user_id,
                    {"revision_number": draft.revision_number, "visibility": payload.visibility.value},
                ),
                ai_timeline_event(
                    event_type="coach_review_approved",
                    athlete_id=review.athlete_id,
                    review_id=review.id,
                    actor_user_id=user_id,
                    occurred_at=approved_at,
                    metadata=safe_metadata,
                    event_visibility=payload.visibility.value,
                ),
            ]
        )
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def reject(self, review_id: UUID, user_id: UUID, payload: RejectionRequest) -> AIReview:
        if not payload.confirmation:
            raise BadRequestError("Rejection confirmation is required.")
        review = self.get(review_id, user_id, lock=True)
        if review.status == ReviewStatus.REJECTED:
            existing = review.rejection
            if existing and existing.category == payload.category and existing.reason == payload.reason:
                return review
            raise ConflictError("Review has already been rejected with different details.")
        if review.status != ReviewStatus.GENERATED:
            raise BadRequestError("Review is not ready for rejection.")
        if payload.expected_revision_number != review.latest_revision_number:
            raise StaleReviewRevisionError(review.latest_revision_number)
        rejected_at = datetime.now(UTC)
        rejection = ReviewRejection(
            review_id=review.id,
            rejected_by_user_id=user_id,
            category=payload.category,
            reason=payload.reason,
            rejected_at=rejected_at,
        )
        review.status, review.rejected_at = ReviewStatus.REJECTED, rejected_at
        metadata: dict[str, object] = {
            "review_id": str(review.id),
            "video_id": str(review.video_id),
            "practice_session_id": str(review.practice_session_id),
            "review_type": review.review_type.value,
            "rejection_category": payload.category.value,
        }
        self.db.add_all(
            [
                rejection,
                self._audit(
                    review.id,
                    AuditAction.REVIEW_REJECTED,
                    user_id,
                    {"revision_number": review.latest_revision_number, "rejection_category": payload.category.value},
                ),
                ai_timeline_event(
                    event_type="coach_review_rejected",
                    athlete_id=review.athlete_id,
                    review_id=review.id,
                    actor_user_id=user_id,
                    occurred_at=rejected_at,
                    metadata=metadata,
                ),
            ]
        )
        self.db.commit()
        return review

    def approved(self, review: AIReview) -> ApprovedReviewSnapshot:
        if not review.approved_snapshot:
            raise NotFoundError("Approved review snapshot not found.")
        return review.approved_snapshot

    def audit_log(
        self, review: AIReview, page: int, page_size: int, action: AuditAction | None = None
    ) -> tuple[builtins.list[ReviewAuditEvent], int]:
        statement = select(ReviewAuditEvent).where(ReviewAuditEvent.review_id == review.id)
        if action:
            statement = statement.where(ReviewAuditEvent.action_type == action)
        statement = statement.order_by(ReviewAuditEvent.occurred_at.desc())
        total = len(list(self.db.scalars(statement)))
        return list(self.db.scalars(statement.offset((page - 1) * page_size).limit(page_size))), total

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
