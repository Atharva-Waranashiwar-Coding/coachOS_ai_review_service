"""Approved-only review queries for coach progress insights."""

from datetime import datetime
from math import ceil
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.review import AIReview, ApprovedReviewSnapshot, ReviewStatus
from app.schemas.insights import (
    ApprovedReviewInsightItem,
    ApprovedReviewInsightPage,
    ReviewInsightBatchResponse,
)


class ReviewInsightService:
    """Return only immutable approved content required by Athlete Service."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _statement(
        athlete_ids: list[UUID],
        start_date: datetime,
        end_date: datetime,
    ) -> Select[tuple[AIReview, ApprovedReviewSnapshot]]:
        return (
            select(AIReview, ApprovedReviewSnapshot)
            .join(ApprovedReviewSnapshot, ApprovedReviewSnapshot.id == AIReview.approved_snapshot_id)
            .where(
                AIReview.athlete_id.in_(athlete_ids),
                AIReview.status == ReviewStatus.APPROVED,
                ApprovedReviewSnapshot.approved_at >= start_date,
                ApprovedReviewSnapshot.approved_at < end_date,
            )
        )

    def page(
        self,
        athlete_id: UUID,
        start_date: datetime,
        end_date: datetime,
        page: int,
        page_size: int,
    ) -> ApprovedReviewInsightPage:
        statement = self._statement([athlete_id], start_date, end_date)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(
            statement.order_by(ApprovedReviewSnapshot.approved_at.desc(), AIReview.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ApprovedReviewInsightPage(
            items=[self._item(review, snapshot) for review, snapshot in rows],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def batch(
        self,
        athlete_ids: list[UUID],
        start_date: datetime,
        end_date: datetime,
        comparison_start: datetime | None,
        comparison_end: datetime | None,
    ) -> ReviewInsightBatchResponse:
        query_start = comparison_start if comparison_start is not None else start_date
        query_end = max(end_date, comparison_end) if comparison_end is not None else end_date
        rows = self.db.execute(
            self._statement(athlete_ids, query_start, query_end).order_by(
                ApprovedReviewSnapshot.approved_at.desc(), AIReview.id.desc()
            )
        ).all()
        return ReviewInsightBatchResponse(items=[self._item(review, snapshot) for review, snapshot in rows])

    @staticmethod
    def _item(review: AIReview, snapshot: ApprovedReviewSnapshot) -> ApprovedReviewInsightItem:
        return ApprovedReviewInsightItem.model_validate(
            {
                "review_id": review.id,
                "athlete_id": review.athlete_id,
                "review_type": review.review_type,
                "approved_at": snapshot.approved_at,
                "visibility": snapshot.visibility,
                "strengths": snapshot.strengths,
                "improvement_areas": snapshot.improvement_areas,
                "recommended_drills": snapshot.recommended_drills,
                "practice_session_id": review.practice_session_id,
                "video_id": review.video_id,
            }
        )
