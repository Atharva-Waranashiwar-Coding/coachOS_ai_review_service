"""Coach-only HTTP endpoints for review generation and human approval."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_coach, token
from app.models.review import AIReview, AuditAction, ReviewStatus
from app.schemas.review import (
    AllowedActions,
    ApprovalRequest,
    ApprovedReviewContract,
    ApprovedSnapshotRead,
    AthletePreview,
    AuditEventRead,
    AuditPage,
    CurrentUser,
    PreviewRequest,
    RejectionRequest,
    ReviewAccepted,
    ReviewCreate,
    ReviewRead,
    ReviewRevisionCreate,
    ReviewStatusRead,
    RevisionListItem,
    RevisionPage,
    RevisionRead,
)
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


def serialize(review: AIReview, service: ReviewService) -> ReviewRead:
    can_review = review.status == ReviewStatus.GENERATED
    return ReviewRead.model_validate(
        {
            "id": review.id,
            "athlete_id": review.athlete_id,
            "practice_session_id": review.practice_session_id,
            "video_id": review.video_id,
            "status": review.status,
            "review_type": review.review_type,
            "latest_revision_number": review.latest_revision_number,
            "generated_at": review.generated_at or review.generation_completed_at,
            "created_at": review.created_at,
            "approved_at": review.approved_at,
            "rejected_at": review.rejected_at,
            "result": review.result,
            "active_draft": (
                service.get_active_draft(review)
                if review.status in {ReviewStatus.GENERATED, ReviewStatus.APPROVED} and review.result
                else None
            ),
            "approved_snapshot": review.approved_snapshot,
            "rejection_category": review.rejection.category if review.rejection else None,
            "allowed_actions": AllowedActions(
                can_edit=can_review,
                can_preview=review.status in {ReviewStatus.GENERATED, ReviewStatus.APPROVED},
                can_approve=can_review,
                can_reject=can_review,
                can_retry=review.status == ReviewStatus.FAILED,
            ),
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
    service = ReviewService(db)
    return [serialize(review, service) for review in service.list(user.id, athlete_id, video_id, review_status)]


@router.get("/athletes/{athlete_id}/reviews", response_model=list[ReviewRead])
def list_athlete_reviews(
    athlete_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> list[ReviewRead]:
    service = ReviewService(db)
    return [serialize(review, service) for review in service.list(user.id, athlete_id=athlete_id)]


@router.get("/videos/{video_id}/reviews", response_model=list[ReviewRead])
def list_video_reviews(
    video_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> list[ReviewRead]:
    service = ReviewService(db)
    return [serialize(review, service) for review in service.list(user.id, video_id=video_id)]


@router.get("/{review_id}", response_model=ReviewRead)
def get_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(service.get(review_id, user.id), service)


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
        failure_reason="Generation could not be completed." if review.failure_reason else None,
    )


@router.post("/{review_id}/revisions", response_model=RevisionRead, status_code=status.HTTP_201_CREATED)
def create_revision(
    review_id: UUID,
    payload: ReviewRevisionCreate,
    user: CurrentUser = Depends(require_coach),
    db: Session = Depends(get_db),
) -> RevisionRead:
    revision = ReviewService(db).create_revision(review_id, user.id, payload)
    return RevisionRead.model_validate(revision)


@router.get("/{review_id}/revisions", response_model=RevisionPage)
def list_revisions(
    review_id: UUID,
    user: CurrentUser = Depends(require_coach),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> RevisionPage:
    service = ReviewService(db)
    revisions, total = service.list_revisions(service.get(review_id, user.id), page, page_size)
    return RevisionPage(
        items=[RevisionListItem.model_validate(item) for item in revisions], page=page, page_size=page_size, total=total
    )


@router.get("/{review_id}/revisions/{revision_id}", response_model=RevisionRead)
def get_revision(
    review_id: UUID, revision_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> RevisionRead:
    service = ReviewService(db)
    review = service.get(review_id, user.id)
    return RevisionRead.model_validate(service._revision_for_id(review, revision_id))


@router.post("/{review_id}/preview", response_model=AthletePreview)
def preview_review(
    review_id: UUID, payload: PreviewRequest, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> AthletePreview:
    return ReviewService(db).preview(review_id, user.id, payload)


@router.post("/{review_id}/approve", response_model=ApprovedSnapshotRead)
def approve_review(
    review_id: UUID, payload: ApprovalRequest, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ApprovedSnapshotRead:
    return ApprovedSnapshotRead.model_validate(ReviewService(db).approve(review_id, user.id, payload))


@router.post("/{review_id}/reject", response_model=ReviewRead)
def reject_review(
    review_id: UUID,
    payload: RejectionRequest,
    user: CurrentUser = Depends(require_coach),
    db: Session = Depends(get_db),
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(service.reject(review_id, user.id, payload), service)


@router.get("/{review_id}/approved", response_model=ApprovedReviewContract)
def approved_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ApprovedReviewContract:
    service = ReviewService(db)
    review = service.get(review_id, user.id)
    snapshot = service.approved(review)
    return ApprovedReviewContract.model_validate(
        {
            **{column.name: getattr(snapshot, column.name) for column in snapshot.__table__.columns},
            "athlete_id": review.athlete_id,
            "status": "approved",
        }
    )


@router.get("/{review_id}/audit-log", response_model=AuditPage)
def audit_log(
    review_id: UUID,
    user: CurrentUser = Depends(require_coach),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action_type: AuditAction | None = None,
    db: Session = Depends(get_db),
) -> AuditPage:
    service = ReviewService(db)
    events, total = service.audit_log(service.get(review_id, user.id), page, page_size, action_type)
    return AuditPage(
        items=[AuditEventRead.model_validate(event) for event in events], page=page, page_size=page_size, total=total
    )


@router.post("/{review_id}/retry", response_model=ReviewRead)
def retry_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(service.retry(service.get(review_id, user.id)), service)


@router.post("/{review_id}/cancel", response_model=ReviewRead)
def cancel_review(
    review_id: UUID, user: CurrentUser = Depends(require_coach), db: Session = Depends(get_db)
) -> ReviewRead:
    service = ReviewService(db)
    return serialize(
        service.cancel(
            service.get(review_id, user.id),
        ),
        service,
    )
