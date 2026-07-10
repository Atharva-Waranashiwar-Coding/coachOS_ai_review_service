from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.db.session import Base, SessionLocal, engine
from app.models.outbox import OutboxEvent
from app.models.review import AIReview, JobStatus, ReviewGenerationJob, ReviewStatus, ReviewType
from app.schemas.review import DraftUpdate, ReviewCreate
from app.services.review_service import ReviewService


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def payload() -> ReviewCreate:
    return ReviewCreate(
        athlete_id=uuid4(),
        practice_session_id=uuid4(),
        video_id=uuid4(),
        review_type=ReviewType.GENERAL,
        coach_context="Keep feedback concise.",
        session_objectives=["Balanced posture"],
        manual_observations=["Athlete maintained a steady setup."],
    )


def draft() -> DraftUpdate:
    return DraftUpdate(
        summary="A focused coaching draft.",
        observations=[
            {
                "title": "Setup",
                "description": "Steady setup in supplied notes.",
                "category": "technique",
                "priority": "medium",
                "confidence": 0.6,
                "evidence": "Coach observation",
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
    )


def test_request_is_idempotent_and_creates_job_and_outbox(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ReviewService,
        "_context_snapshot",
        lambda *_: {"athlete": {"preferred_name": "Avery"}, "video": {}, "practice_session": {}},
    )
    user_id = uuid4()
    with SessionLocal() as db:
        service = ReviewService(db)
        request = payload()
        created = service.create(request, user_id, "token", "retry-key")
        repeated = service.create(request, user_id, "token", "retry-key")

        assert repeated.id == created.id

        # The second payload is intentionally distinct UUIDs; a reused key must be rejected.
        with pytest.raises(ConflictError):
            service.create(payload(), user_id, "token", "retry-key")

        assert db.query(AIReview).count() == 1
        assert db.query(ReviewGenerationJob).one().status == JobStatus.PENDING
        assert db.query(OutboxEvent).one().event_type == "ai_review_requested"


def test_revision_and_approval_emit_coach_events(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ReviewService, "_context_snapshot", lambda *_: {"athlete": {}, "video": {}, "practice_session": {}}
    )
    user_id = uuid4()
    with SessionLocal() as db:
        service = ReviewService(db)
        review = service.create(payload(), user_id, "token", None)
        review.status = ReviewStatus.GENERATED
        db.commit()

        revision = service.revise(review, draft(), user_id)
        approved = service.approve(review, user_id)

        assert revision.revision_number == 1
        assert approved.status == ReviewStatus.APPROVED
        assert {event.event_type for event in db.query(OutboxEvent).all()} == {
            "ai_review_requested",
            "coach_review_edited",
            "coach_review_approved",
        }
