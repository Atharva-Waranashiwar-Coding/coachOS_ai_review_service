"""Safe review insight endpoints for coach and Athlete Service aggregation."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.dependencies.auth import require_coach, token
from app.dependencies.internal_auth import InternalServiceIdentity, require_insight_service
from app.integrations.athlete_service import AthleteServiceClient
from app.schemas.insights import (
    ApprovedReviewInsightPage,
    ReviewInsightBatchRequest,
    ReviewInsightBatchResponse,
)
from app.schemas.review import CurrentUser
from app.services.review_insight_service import ReviewInsightService

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/athletes/{athlete_id}/approved-reviews", response_model=ApprovedReviewInsightPage)
def approved_reviews(
    athlete_id: UUID,
    start_date: datetime,
    end_date: datetime,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=settings.max_page_size),
    _: CurrentUser = Depends(require_coach),
    bearer_token: str = Depends(token),
    db: Session = Depends(get_db),
) -> ApprovedReviewInsightPage:
    AthleteServiceClient().verify_coach_access(athlete_id, bearer_token)
    return ReviewInsightService(db).page(athlete_id, start_date, end_date, page, page_size)


@router.post("/athletes/approved-review-summary", response_model=ReviewInsightBatchResponse)
def approved_review_batch(
    payload: ReviewInsightBatchRequest,
    _: InternalServiceIdentity = Depends(require_insight_service),
    db: Session = Depends(get_db),
) -> ReviewInsightBatchResponse:
    return ReviewInsightService(db).batch(
        payload.athlete_ids,
        payload.start_date,
        payload.end_date,
        payload.comparison_start,
        payload.comparison_end,
    )
