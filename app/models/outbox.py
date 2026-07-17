from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import postgres_enum


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_status_available", "status", "available_at"),
        Index("ix_outbox_created_at", "created_at"),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100), default="athlete-timeline")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    status: Mapped[OutboxStatus] = mapped_column(
        postgres_enum(OutboxStatus, name="outbox_status"), default=OutboxStatus.PENDING
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
