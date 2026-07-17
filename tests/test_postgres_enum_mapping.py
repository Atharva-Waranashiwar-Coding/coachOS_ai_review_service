import os

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select, text, update

from app.models.outbox import OutboxEvent, OutboxStatus
from app.models.review import JobStatus, ReviewGenerationJob


def _postgres_engine():
    url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is required for PostgreSQL enum integration tests")
    return create_engine(url)


def test_job_and_outbox_statuses_round_trip_as_lowercase_postgres_values():
    engine = _postgres_engine()
    metadata = MetaData()
    jobs = Table(
        "test_review_job_enum_mapping",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", ReviewGenerationJob.__table__.c.status.type, nullable=False),
    )
    outbox = Table(
        "test_review_outbox_enum_mapping",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", OutboxEvent.__table__.c.status.type, nullable=False),
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TEMP TABLE test_review_job_enum_mapping (id integer PRIMARY KEY, status review_job_status NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TEMP TABLE test_review_outbox_enum_mapping (id integer PRIMARY KEY, status outbox_status NOT NULL)"
            )
        )

        connection.execute(jobs.insert().values(id=1, status=JobStatus.PENDING))
        assert connection.scalar(select(jobs.c.status).where(jobs.c.status == JobStatus.PENDING)) is JobStatus.PENDING
        assert (
            connection.scalar(text("SELECT status::text FROM test_review_job_enum_mapping WHERE id = 1")) == "pending"
        )
        connection.execute(update(jobs).where(jobs.c.id == 1).values(status=JobStatus.PROCESSING))
        assert (
            connection.scalar(text("SELECT status::text FROM test_review_job_enum_mapping WHERE id = 1"))
            == "processing"
        )

        connection.execute(outbox.insert().values(id=1, status=OutboxStatus.PENDING))
        assert (
            connection.scalar(select(outbox.c.status).where(outbox.c.status == OutboxStatus.PENDING))
            is OutboxStatus.PENDING
        )
        connection.execute(update(outbox).where(outbox.c.id == 1).values(status=OutboxStatus.PROCESSING))
        assert (
            connection.scalar(text("SELECT status::text FROM test_review_outbox_enum_mapping WHERE id = 1"))
            == "processing"
        )

    engine.dispose()
