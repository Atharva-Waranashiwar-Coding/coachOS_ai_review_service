"""Athlete-only immutable approved feedback endpoints."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.dependencies.current_athlete import get_current_athlete_identity
from app.integrations.athlete_service import AthleteIdentity
from app.models.review import ReviewType
from app.schemas.athlete_feedback import AthleteFeedbackDetail, AthleteFeedbackPage
from app.services.athlete_feedback_service import AthleteFeedbackService

router = APIRouter(prefix="/athlete/reviews", tags=["athlete-feedback"])


@router.get("", response_model=AthleteFeedbackPage)
def list_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    review_type: ReviewType | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    athlete: AthleteIdentity = Depends(get_current_athlete_identity),
    db: Session = Depends(get_db),
) -> AthleteFeedbackPage:
    return AthleteFeedbackService(db).list(
        athlete.id,
        page=page,
        page_size=page_size,
        review_type=review_type,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{review_id}", response_model=AthleteFeedbackDetail)
def get_feedback(
    review_id: UUID,
    athlete: AthleteIdentity = Depends(get_current_athlete_identity),
    db: Session = Depends(get_db),
) -> AthleteFeedbackDetail:
    return AthleteFeedbackService(db).detail(athlete.id, review_id)
