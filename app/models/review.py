"""Persistent AI review workflow models owned by the AI Review Service."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
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


class ReviewVisibility(StrEnum):
    COACH_ONLY = "coach_only"
    ATHLETE_VISIBLE = "athlete_visible"


class RejectionCategory(StrEnum):
    INACCURATE = "inaccurate"
    INSUFFICIENT = "insufficient"
    UNSAFE = "unsafe"
    IRRELEVANT = "irrelevant"
    TOO_GENERIC = "too_generic"
    INADEQUATE_CONTEXT = "inadequate_context"
    OTHER = "other"


class AuditAction(StrEnum):
    REVIEW_GENERATED = "review_generated"
    REVISION_CREATED = "revision_created"
    PREVIEW_REQUESTED = "preview_requested"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"


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
    latest_revision_number: Mapped[int] = mapped_column(Integer, default=0)
    approved_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("approved_review_snapshots.id", use_alter=True, name="fk_review_approved_snapshot"), nullable=True
    )
    coach_context: Mapped[str | None] = mapped_column(Text)
    session_objectives: Mapped[list[Any]] = mapped_column(Json, default=list)
    requested_focus_areas: Mapped[list[Any]] = mapped_column(Json, default=list)
    manual_observations: Mapped[list[Any]] = mapped_column(Json, default=list)
    transcript: Mapped[str | None] = mapped_column(Text)
    frame_observations: Mapped[list[Any]] = mapped_column(Json, default=list)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    model_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    generation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped["ReviewResult | None"] = relationship(back_populates="review")
    revisions: Mapped[list["ReviewRevision"]] = relationship(
        back_populates="review", order_by="ReviewRevision.revision_number"
    )
    approved_snapshot: Mapped["ApprovedReviewSnapshot | None"] = relationship(
        foreign_keys=[approved_snapshot_id], post_update=True
    )
    rejection: Mapped["ReviewRejection | None"] = relationship(back_populates="review", uselist=False)
    audit_events: Mapped[list["ReviewAuditEvent"]] = relationship(back_populates="review")


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
        CheckConstraint("revision_number > 0", name="ck_revision_number_positive"),
        CheckConstraint(
            "based_on_revision_number IS NULL OR based_on_revision_number < revision_number",
            name="ck_revision_based_on_lower",
        ),
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
    athlete_message: Mapped[str | None] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    based_on_revision_number: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    review: Mapped[AIReview] = relationship(back_populates="revisions")


class ApprovedReviewSnapshot(Base):
    __tablename__ = "approved_review_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("ai_reviews.id"), unique=True)
    source_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("review_revisions.id"))
    approved_by_user_id: Mapped[UUID]
    summary: Mapped[str] = mapped_column(Text)
    observations: Mapped[list[Any]] = mapped_column(Json)
    strengths: Mapped[list[Any]] = mapped_column(Json)
    improvement_areas: Mapped[list[Any]] = mapped_column(Json)
    recommended_drills: Mapped[list[Any]] = mapped_column(Json)
    athlete_message: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[ReviewVisibility] = mapped_column(Enum(ReviewVisibility, name="review_visibility"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewRejection(Base):
    __tablename__ = "review_rejections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("ai_reviews.id"), unique=True)
    rejected_by_user_id: Mapped[UUID]
    category: Mapped[RejectionCategory] = mapped_column(Enum(RejectionCategory, name="review_rejection_category"))
    reason: Mapped[str | None] = mapped_column(Text)
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    review: Mapped[AIReview] = relationship(back_populates="rejection")


class ReviewAuditEvent(Base):
    __tablename__ = "review_audit_events"
    __table_args__ = (
        Index("ix_audit_review_occurred", "review_id", "occurred_at"),
        Index("ix_audit_actor", "actor_user_id"),
        Index("ix_audit_action", "action_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("ai_reviews.id"))
    actor_user_id: Mapped[UUID | None]
    action_type: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="review_audit_action"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", Json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    review: Mapped[AIReview] = relationship(back_populates="audit_events")


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
