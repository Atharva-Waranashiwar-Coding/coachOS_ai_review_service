from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, StaleReviewRevisionError
from app.db.session import Base, SessionLocal, engine
from app.models.outbox import OutboxEvent
from app.models.review import (
    AIReview,
    AuditAction,
    ReviewAuditEvent,
    ReviewResult,
    ReviewStatus,
    ReviewType,
    ReviewVisibility,
)
from app.schemas.review import ApprovalRequest, PreviewRequest, RejectionRequest, ReviewCreate, ReviewRevisionCreate
from app.services.review_service import ReviewService


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def request_payload() -> ReviewCreate:
    return ReviewCreate(
        athlete_id=uuid4(),
        practice_session_id=uuid4(),
        video_id=uuid4(),
        review_type=ReviewType.GENERAL,
        coach_context="Keep feedback concise.",
        session_objectives=["Balanced posture"],
    )


def revision_payload(expected: int = 0) -> ReviewRevisionCreate:
    return ReviewRevisionCreate(
        expected_revision_number=expected,
        summary="A focused coaching draft.",
        observations=[
            {
                "title": "Setup",
                "description": "Steady setup.",
                "category": "technique",
                "priority": "medium",
                "confidence": 0.6,
                "coach_verified": True,
            }
        ],
        strengths=[{"title": "Consistency", "description": "Good repeatability."}],
        improvement_areas=[{"title": "Timing", "description": "Continue timing work.", "priority": "medium"}],
        recommended_drills=[
            {
                "name": "Dry reps",
                "description": "Repeat controlled movements.",
                "reason": "Reinforces timing.",
                "difficulty": "beginner",
            }
        ],
        coach_notes="Private cue for the next session.",
        athlete_message="Keep building on your steady setup.",
        change_summary="Clarified setup feedback.",
    )


def generated_review(service: ReviewService, user_id):
    review = service.create(request_payload(), user_id, "token", None)
    review.status = ReviewStatus.GENERATED
    review.result = ReviewResult(
        review_id=review.id,
        summary="Generated baseline.",
        observations=[],
        strengths=[],
        improvement_areas=[],
        recommended_drills=[],
        limitations=["Based on supplied context."],
    )
    service.db.commit()
    return review


def test_request_is_idempotent_and_creates_job_and_outbox(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ReviewService, "_context_snapshot", lambda *_: {"athlete": {}, "video": {}, "practice_session": {}}
    )
    user_id = uuid4()
    with SessionLocal() as db:
        service = ReviewService(db)
        request = request_payload()
        created = service.create(request, user_id, "token", "retry-key")
        assert service.create(request, user_id, "token", "retry-key").id == created.id
        with pytest.raises(ConflictError):
            service.create(request_payload(), user_id, "token", "retry-key")
        assert db.query(AIReview).count() == 1
        assert db.query(OutboxEvent).one().event_type == "ai_review_requested"


def test_revisions_are_immutable_and_stale_edits_are_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ReviewService, "_context_snapshot", lambda *_: {"athlete": {}, "video": {}, "practice_session": {}}
    )
    with SessionLocal() as db:
        service = ReviewService(db)
        review = generated_review(service, uuid4())
        first = service.create_revision(review.id, review.requested_by_user_id, revision_payload())
        second = service.create_revision(review.id, review.requested_by_user_id, revision_payload(expected=1))
        with pytest.raises(StaleReviewRevisionError):
            service.create_revision(review.id, review.requested_by_user_id, revision_payload())
        assert (first.revision_number, second.revision_number, review.latest_revision_number) == (1, 2, 2)
        assert db.query(ReviewAuditEvent).filter_by(action_type=AuditAction.REVISION_CREATED).count() == 2


def test_approval_creates_immutable_snapshot_without_private_notes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ReviewService, "_context_snapshot", lambda *_: {"athlete": {}, "video": {}, "practice_session": {}}
    )
    with SessionLocal() as db:
        service = ReviewService(db)
        review = generated_review(service, uuid4())
        revision = service.create_revision(review.id, review.requested_by_user_id, revision_payload())
        snapshot = service.approve(
            review.id,
            review.requested_by_user_id,
            ApprovalRequest(
                expected_revision_number=1,
                revision_id=revision.id,
                visibility=ReviewVisibility.ATHLETE_VISIBLE,
                confirmation=True,
            ),
        )
        assert snapshot.athlete_message == "Keep building on your steady setup."
        assert not hasattr(snapshot, "coach_notes")
        assert review.status == ReviewStatus.APPROVED
        assert db.query(OutboxEvent).filter_by(event_type="coach_review_approved").count() == 1
        assert (
            service.approve(
                review.id,
                review.requested_by_user_id,
                ApprovalRequest(
                    expected_revision_number=1,
                    revision_id=revision.id,
                    visibility=ReviewVisibility.ATHLETE_VISIBLE,
                    confirmation=True,
                ),
            ).id
            == snapshot.id
        )


def test_rejection_is_private_and_records_safe_timeline_metadata(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ReviewService, "_context_snapshot", lambda *_: {"athlete": {}, "video": {}, "practice_session": {}}
    )
    with SessionLocal() as db:
        service = ReviewService(db)
        review = generated_review(service, uuid4())
        rejected = service.reject(
            review.id,
            review.requested_by_user_id,
            RejectionRequest(
                category="inaccurate", reason="Private coach detail", expected_revision_number=0, confirmation=True
            ),
        )
        event = db.query(OutboxEvent).filter_by(event_type="coach_review_rejected").one()
        assert rejected.status == ReviewStatus.REJECTED
        assert "Private coach detail" not in str(event.payload)


def test_preview_excludes_private_notes_and_creates_audit_event(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ReviewService, "_context_snapshot", lambda *_: {"athlete": {}, "video": {}, "practice_session": {}}
    )
    with SessionLocal() as db:
        service = ReviewService(db)
        review = generated_review(service, uuid4())
        service.create_revision(review.id, review.requested_by_user_id, revision_payload())
        preview = service.preview(
            review.id,
            review.requested_by_user_id,
            PreviewRequest(visibility=ReviewVisibility.ATHLETE_VISIBLE),
        )
        assert preview.athlete_message == "Keep building on your steady setup."
        assert "coach_notes" not in preview.model_dump()
        assert db.query(ReviewAuditEvent).filter_by(action_type=AuditAction.PREVIEW_REQUESTED).count() == 1
