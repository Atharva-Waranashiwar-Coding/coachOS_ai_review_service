"""Read immutable, athlete-visible approved feedback snapshots."""

from datetime import UTC, date, datetime, time
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.review import AIReview, ApprovedReviewSnapshot, ReviewStatus, ReviewType, ReviewVisibility
from app.schemas.athlete_feedback import (
    AthleteFeedbackDetail,
    AthleteFeedbackPage,
    AthleteFeedbackSummary,
    AthleteSessionContext,
)


class AthleteFeedbackService:
    """Enforce snapshot status, visibility, and athlete ownership in SQL."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _base(athlete_id: UUID) -> Select[tuple[AIReview, ApprovedReviewSnapshot]]:
        return (
            select(AIReview, ApprovedReviewSnapshot)
            .join(
                ApprovedReviewSnapshot,
                ApprovedReviewSnapshot.id == AIReview.approved_snapshot_id,
            )
            .where(
                AIReview.athlete_id == athlete_id,
                AIReview.status == ReviewStatus.APPROVED,
                ApprovedReviewSnapshot.visibility == ReviewVisibility.ATHLETE_VISIBLE,
            )
        )

    def list(
        self,
        athlete_id: UUID,
        *,
        page: int,
        page_size: int,
        review_type: ReviewType | None,
        start_date: date | None,
        end_date: date | None,
    ) -> AthleteFeedbackPage:
        statement = self._base(athlete_id)
        if review_type:
            statement = statement.where(AIReview.review_type == review_type)
        if start_date:
            statement = statement.where(
                ApprovedReviewSnapshot.approved_at >= datetime.combine(start_date, time.min, tzinfo=UTC)
            )
        if end_date:
            statement = statement.where(
                ApprovedReviewSnapshot.approved_at <= datetime.combine(end_date, time.max, tzinfo=UTC)
            )
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(
            statement.order_by(
                ApprovedReviewSnapshot.approved_at.desc(),
                AIReview.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return AthleteFeedbackPage(
            items=[self._summary(review, snapshot) for review, snapshot in rows],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    def detail(self, athlete_id: UUID, review_id: UUID) -> AthleteFeedbackDetail:
        row = self.db.execute(self._base(athlete_id).where(AIReview.id == review_id)).one_or_none()
        if not row:
            raise NotFoundError("Approved feedback not found.")
        review, snapshot = row
        return AthleteFeedbackDetail.model_validate(
            {
                "review_id": review.id,
                "review_type": review.review_type,
                "summary": snapshot.summary,
                "observations": snapshot.observations,
                "strengths": snapshot.strengths,
                "improvement_areas": snapshot.improvement_areas,
                "recommended_drills": snapshot.recommended_drills,
                "athlete_message": snapshot.athlete_message,
                "approved_at": snapshot.approved_at,
                "session_context": self._session_context(review),
            }
        )

    @classmethod
    def _summary(cls, review: AIReview, snapshot: ApprovedReviewSnapshot) -> AthleteFeedbackSummary:
        excerpt = snapshot.summary if len(snapshot.summary) <= 240 else f"{snapshot.summary[:237].rstrip()}..."
        return AthleteFeedbackSummary(
            review_id=review.id,
            review_type=review.review_type,
            athlete_message=snapshot.athlete_message,
            summary_excerpt=excerpt,
            approved_at=snapshot.approved_at,
            session_context=cls._session_context(review),
        )

    @staticmethod
    def _session_context(review: AIReview) -> AthleteSessionContext | None:
        raw = review.context_snapshot.get("practice_session")
        if not isinstance(raw, dict):
            return None
        safe = {key: raw.get(key) for key in ("title", "session_type", "session_date", "location")}
        if not any(value is not None for value in safe.values()):
            return None
        return AthleteSessionContext.model_validate(safe)
