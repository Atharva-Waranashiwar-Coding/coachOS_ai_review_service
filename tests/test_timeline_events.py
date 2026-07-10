import os

os.environ.update(
    {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "ATHLETE_SERVICE_INTERNAL_URL": "http://athlete.test",
        "INTERNAL_SERVICE_TOKEN": "test",
    }
)
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.services.timeline_events import ai_timeline_event


def test_generated_review_is_coach_only_and_safe():
    event = ai_timeline_event(
        event_type="ai_review_generated",
        athlete_id=uuid4(),
        review_id=uuid4(),
        actor_user_id=None,
        occurred_at=datetime.now(UTC),
        metadata={"review_id": "safe"},
    )
    assert event.payload["visibility"] == "coach_only" and "raw_output" not in event.payload


def test_approval_is_athlete_visible():
    event = ai_timeline_event(
        event_type="coach_review_approved",
        athlete_id=uuid4(),
        review_id=uuid4(),
        actor_user_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )
    assert event.payload["visibility"] == "athlete_visible"


def test_unsafe_metadata_rejected():
    with pytest.raises(ValueError):
        ai_timeline_event(
            event_type="ai_review_generated",
            athlete_id=uuid4(),
            review_id=uuid4(),
            actor_user_id=None,
            occurred_at=datetime.now(UTC),
            metadata={"raw_model_output": "secret"},
        )
