"""Data models for the AI review service."""

from app.models.outbox import OutboxEvent, OutboxStatus

__all__ = ["OutboxEvent", "OutboxStatus"]
