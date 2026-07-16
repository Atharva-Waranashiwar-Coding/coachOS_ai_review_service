"""Athlete-visible approved snapshot filtering and privacy tests."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.core.exceptions import NotFoundError
from app.db.session import Base, SessionLocal, engine
from app.integrations.athlete_service import AthleteServiceClient
from app.models.review import (
    AIReview,
    ApprovedReviewSnapshot,
    ReviewStatus,
    ReviewType,
    ReviewVisibility,
)
from app.services.athlete_feedback_service import AthleteFeedbackService


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def approved_review(
    *,
    athlete_id,
    visibility: ReviewVisibility,
    status: ReviewStatus = ReviewStatus.APPROVED,
) -> AIReview:
    review_id = uuid4()
    review = AIReview(
        id=review_id,
        athlete_id=athlete_id,
        practice_session_id=uuid4(),
        video_id=uuid4(),
        requested_by_user_id=uuid4(),
        status=status,
        review_type=ReviewType.FIELDING,
        request_fingerprint=uuid4().hex,
        prompt_version="test",
        context_snapshot={
            "practice_session": {
                "title": "Infield work",
                "session_type": "practice",
                "session_date": "2026-07-15",
                "location": "Field 2",
                "private_internal_value": "hidden",
            }
        },
    )
    snapshot = ApprovedReviewSnapshot(
        review_id=review_id,
        approved_by_user_id=uuid4(),
        summary="Approved athlete summary.",
        observations=[
            {
                "title": "Ready position",
                "description": "Balanced setup.",
                "category": "technique",
                "priority": "medium",
                "confidence": 0.98,
                "evidence": "Private evidence",
                "coach_verified": True,
            }
        ],
        strengths=[{"title": "First step", "description": "Quick movement."}],
        improvement_areas=[
            {
                "title": "Glove path",
                "description": "Stay lower.",
                "priority": "medium",
            }
        ],
        recommended_drills=[
            {
                "name": "Crossover reps",
                "description": "Controlled repetitions.",
                "reason": "Builds movement quality.",
                "difficulty": "beginner",
            }
        ],
        athlete_message="Keep building on your setup.",
        visibility=visibility,
        approved_at=datetime.now(UTC),
    )
    review.approved_snapshot = snapshot
    review.approved_snapshot_id = snapshot.id
    return review


def test_list_only_returns_current_athlete_visible_approved_snapshots() -> None:
    athlete_id = uuid4()
    with SessionLocal() as db:
        visible = approved_review(
            athlete_id=athlete_id,
            visibility=ReviewVisibility.ATHLETE_VISIBLE,
        )
        db.add_all(
            [
                visible,
                approved_review(
                    athlete_id=athlete_id,
                    visibility=ReviewVisibility.COACH_ONLY,
                ),
                approved_review(
                    athlete_id=uuid4(),
                    visibility=ReviewVisibility.ATHLETE_VISIBLE,
                ),
                approved_review(
                    athlete_id=athlete_id,
                    visibility=ReviewVisibility.ATHLETE_VISIBLE,
                    status=ReviewStatus.GENERATED,
                ),
            ]
        )
        db.commit()

        page = AthleteFeedbackService(db).list(
            athlete_id,
            page=1,
            page_size=20,
            review_type=None,
            start_date=None,
            end_date=None,
        )

        assert page.total == 1
        assert page.items[0].review_id == visible.id


def test_detail_excludes_confidence_evidence_and_private_metadata() -> None:
    athlete_id = uuid4()
    with SessionLocal() as db:
        review = approved_review(
            athlete_id=athlete_id,
            visibility=ReviewVisibility.ATHLETE_VISIBLE,
        )
        db.add(review)
        db.commit()

        payload = AthleteFeedbackService(db).detail(athlete_id, review.id).model_dump()

        assert "confidence" not in payload["observations"][0]
        assert "evidence" not in payload["observations"][0]
        assert "coach_notes" not in payload
        assert "model_name" not in payload
        assert "revision" not in str(payload)
        assert payload["session_context"] == {
            "title": "Infield work",
            "session_type": "practice",
            "session_date": datetime(2026, 7, 15).date(),
            "location": "Field 2",
        }


def test_inaccessible_detail_is_hidden_as_not_found() -> None:
    athlete_id = uuid4()
    with SessionLocal() as db:
        coach_only = approved_review(
            athlete_id=athlete_id,
            visibility=ReviewVisibility.COACH_ONLY,
        )
        db.add(coach_only)
        db.commit()

        with pytest.raises(NotFoundError):
            AthleteFeedbackService(db).detail(athlete_id, coach_only.id)


def test_identity_client_forwards_bearer_and_parses_only_athlete_id() -> None:
    athlete_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer athlete-token"
        assert request.url.path == "/api/v1/athlete/me"
        return httpx.Response(
            200,
            json={
                "id": str(athlete_id),
                "first_name": "Maya",
                "injury_notes": "not part of identity contract",
            },
        )

    client = AthleteServiceClient(httpx.Client(transport=httpx.MockTransport(handler)))

    assert client.resolve_current_athlete("athlete-token").id == athlete_id
