"""Approved review insight contract tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.session import Base, SessionLocal, engine
from app.models.review import AIReview, ApprovedReviewSnapshot, ReviewStatus, ReviewType, ReviewVisibility
from app.services.review_insight_service import ReviewInsightService


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def review(athlete_id, approved_at, *, status=ReviewStatus.APPROVED):
    review_id = uuid4()
    item = AIReview(
        id=review_id,
        athlete_id=athlete_id,
        practice_session_id=uuid4(),
        video_id=uuid4(),
        requested_by_user_id=uuid4(),
        status=status,
        review_type=ReviewType.HITTING,
        request_fingerprint=uuid4().hex,
        prompt_version="test",
    )
    snapshot = ApprovedReviewSnapshot(
        review_id=review_id,
        approved_by_user_id=uuid4(),
        summary="Approved.",
        observations=[],
        strengths=[
            {
                "title": "Balance",
                "description": "Stable base.",
                "taxonomy_code": "hitting.balance",
            }
        ],
        improvement_areas=[
            {
                "title": "Timing",
                "description": "Continue timing work.",
                "priority": "high",
                "taxonomy_code": "hitting.timing",
                "evidence": "must not serialize",
            }
        ],
        recommended_drills=[],
        visibility=ReviewVisibility.COACH_ONLY,
        approved_at=approved_at,
    )
    item.approved_snapshot = snapshot
    item.approved_snapshot_id = snapshot.id
    return item


def test_insights_include_only_approved_rows_in_half_open_range():
    now = datetime.now(UTC)
    athlete_id = uuid4()
    with SessionLocal() as db:
        included = review(athlete_id, now)
        db.add_all(
            [
                included,
                review(athlete_id, now - timedelta(days=40)),
                review(athlete_id, now + timedelta(days=1)),
                review(athlete_id, now, status=ReviewStatus.GENERATED),
                review(uuid4(), now),
            ]
        )
        db.commit()

        page = ReviewInsightService(db).page(
            athlete_id,
            now - timedelta(days=30),
            now + timedelta(hours=1),
            1,
            20,
        )

        assert page.total == 1
        assert page.items[0].review_id == included.id
        assert page.items[0].strengths[0].taxonomy_code == "hitting.balance"
        payload = page.items[0].model_dump()
        assert "evidence" not in payload["improvement_areas"][0]
        assert "model_name" not in payload


def test_batch_is_bounded_to_requested_athletes_and_comparison_period():
    now = datetime.now(UTC)
    athlete_ids = [uuid4(), uuid4()]
    with SessionLocal() as db:
        db.add_all(
            [
                review(athlete_ids[0], now - timedelta(days=5)),
                review(athlete_ids[1], now - timedelta(days=35)),
                review(uuid4(), now - timedelta(days=5)),
            ]
        )
        db.commit()

        response = ReviewInsightService(db).batch(
            athlete_ids,
            now - timedelta(days=30),
            now,
            now - timedelta(days=60),
            now - timedelta(days=30),
        )

        assert {item.athlete_id for item in response.items} == set(athlete_ids)
