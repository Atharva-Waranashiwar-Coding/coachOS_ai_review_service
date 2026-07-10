"""Persistent review, revision, and asynchronous generation job models."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

Json = JSON().with_variant(JSONB, "postgresql")


class ReviewStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    GENERATED = "generated"
    FAILED = "failed"
    CANCELLED = "cancelled"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewType(StrEnum):
    GENERAL = "general"
    HITTING = "hitting"
    PITCHING = "pitching"
    FIELDING = "fielding"
    THROWING = "throwing"
    FOOTWORK = "footwork"
    MOBILITY = "mobility"
    STRENGTH = "strength"
    DECISION_MAKING = "decision_making"


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIReview(Base):
    __tablename__ = "ai_reviews"
    __table_args__ = (
        Index("ix_reviews_athlete", "athlete_id"),
        Index("ix_reviews_video", "video_id"),
        Index("ix_reviews_session", "practice_session_id"),
        Index("ix_reviews_status", "status"),
        Index("ix_reviews_requested_by", "requested_by_user_id"),
        Index("ix_reviews_created", "created_at"),
        UniqueConstraint("requested_by_user_id", "idempotency_key", name="uq_review_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    athlete_id: Mapped[UUID]
    practice_session_id: Mapped[UUID]
    video_id: Mapped[UUID]
    requested_by_user_id: Mapped[UUID]
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, name="review_status"), default=ReviewStatus.PENDING)
    review_type: Mapped[ReviewType] = mapped_column(Enum(ReviewType, name="review_type"))
    coach_context: Mapped[str | None] = mapped_column(Text)
    session_objectives: Mapped[list[Any]] = mapped_column(Json, default=list)
    requested_focus_areas: Mapped[list[Any]] = mapped_column(Json, default=list)
    manual_observations: Mapped[list[Any]] = mapped_column(Json, default=list)
    transcript: Mapped[str | None] = mapped_column(Text)
    frame_observations: Mapped[list[Any]] = mapped_column(Json, default=list)
    # This bounded, safe snapshot is captured at request time; workers never fetch or transmit video bytes.
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    model_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    generation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped["ReviewResult | None"] = relationship(back_populates="review")
    revisions: Mapped[list["ReviewRevision"]] = relationship(back_populates="review")


class ReviewResult(Base):
    __tablename__ = "review_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("ai_reviews.id"), unique=True)
    summary: Mapped[str] = mapped_column(Text)
    observations: Mapped[list[Any]] = mapped_column(Json)
    strengths: Mapped[list[Any]] = mapped_column(Json)
    improvement_areas: Mapped[list[Any]] = mapped_column(Json)
    recommended_drills: Mapped[list[Any]] = mapped_column(Json)
    limitations: Mapped[list[Any]] = mapped_column(Json)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    input_token_count: Mapped[int | None] = mapped_column(Integer)
    output_token_count: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    raw_provider_response: Mapped[dict[str, Any] | None] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    review: Mapped[AIReview] = relationship(back_populates="result")


class ReviewRevision(Base):
    __tablename__ = "review_revisions"
    __table_args__ = (
        UniqueConstraint("review_id", "revision_number", name="uq_revision_number"),
        Index("ix_revision_review_number", "review_id", "revision_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("ai_reviews.id"))
    revision_number: Mapped[int]
    edited_by_user_id: Mapped[UUID]
    summary: Mapped[str] = mapped_column(Text)
    observations: Mapped[list[Any]] = mapped_column(Json)
    strengths: Mapped[list[Any]] = mapped_column(Json)
    improvement_areas: Mapped[list[Any]] = mapped_column(Json)
    recommended_drills: Mapped[list[Any]] = mapped_column(Json)
    coach_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    review: Mapped[AIReview] = relationship(back_populates="revisions")


class ReviewGenerationJob(Base):
    __tablename__ = "review_generation_jobs"
    __table_args__ = (Index("ix_job_status_available", "status", "available_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("ai_reviews.id"), unique=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="review_job_status"), default=JobStatus.PENDING)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
