"""Coach-facing AI review API."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_coach, token
from app.models.review import AIReview, ReviewStatus
from app.schemas.review import (
    CurrentUser,
    DraftUpdate,
    RejectRequest,
    ReviewAccepted,
    ReviewCreate,
    ReviewRead,
    ReviewStatusRead,
    RevisionRead,
)
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


def serialize(review: AIReview) -> ReviewRead:
    latest = max(review.revisions, key=lambda revision: revision.revision_number) if review.revisions else None
    return ReviewRead.model_validate(
        {
            **{column.name: getattr(review, column.name) for column in review.__table__.columns},
            "result": review.result,
            "latest_revision": latest,
        }
    )


@router.post("", response_model=ReviewAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_review(
    payload: ReviewCreate,
    user: CurrentUser = Depends(require_coach),
    bearer_token: str = Depends(token),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255),
    db: Session = Depends(get_db),
) -> ReviewAccepted:
    review = ReviewService(db).create(payload, user.id, bearer_token, idempotency_key)
    return ReviewAccepted(
        review_id=review.id,
        status=review.status,
        created_at=review.created_at,
        status_url=f"/api/v1/reviews/{review.id}/status",
    )


@router.get("", response_model=list[ReviewRead])
def list_reviews(
    user: CurrentUser = Depends(require_coach),
    athlete_id: UUID | None = None,
    video_id: UUID | None = None,
    review_status: ReviewStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[ReviewRead]:
    return [serialize(review) for review in ReviewService(db).list(user.id, athlete_id, video_id, review_status)]


@router.get("/athletes/{athlete_id}/reviews", response_model=list[ReviewRead])
def list_athlete_reviews(
    athlete_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> list[ReviewRead]:
    return [serialize(review) for review in ReviewService(db).list(user.id, athlete_id=athlete_id)]


@router.get("/videos/{video_id}/reviews", response_model=list[ReviewRead])
def list_video_reviews(
    video_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> list[ReviewRead]:
    return [serialize(review) for review in ReviewService(db).list(user.id, video_id=video_id)]


@router.get("/{review_id}", response_model=ReviewRead)
def get_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    return serialize(ReviewService(db).get(review_id, user.id))


@router.get("/{review_id}/status", response_model=ReviewStatusRead)
def get_review_status(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewStatusRead:
    review = ReviewService(db).get(review_id, user.id)
    return ReviewStatusRead(
        review_id=review.id,
        status=review.status,
        generation_started_at=review.generation_started_at,
        generation_completed_at=review.generation_completed_at,
        retryable=review.status == ReviewStatus.FAILED,
        failure_reason=review.failure_reason,
    )


@router.patch("/{review_id}/draft", response_model=RevisionRead)
def update_draft(
    review_id: UUID, payload: DraftUpdate, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> RevisionRead:
    revision = ReviewService(db).revise(ReviewService(db).get(review_id, user.id), payload, user.id)
    return RevisionRead.model_validate(revision)


@router.post("/{review_id}/approve", response_model=ReviewRead)
def approve_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(service.approve(service.get(review_id, user.id), user.id))


@router.post("/{review_id}/reject", response_model=ReviewRead)
def reject_review(
    review_id: UUID, payload: RejectRequest, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(service.reject(service.get(review_id, user.id), user.id, payload.reason))


@router.post("/{review_id}/retry", response_model=ReviewRead)
def retry_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(service.retry(service.get(review_id, user.id)))


@router.post("/{review_id}/cancel", response_model=ReviewRead)
def cancel_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(service.cancel(service.get(review_id, user.id)))
