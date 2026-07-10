from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ai.schemas import GeneratedReview, ImprovementArea, Observation, RecommendedDrill, Strength
from app.models.review import ReviewStatus, ReviewType


class CurrentUser(BaseModel):
    id: UUID
    email: str
    role: str


class ReviewCreate(BaseModel):
    athlete_id: UUID
    practice_session_id: UUID
    video_id: UUID
    review_type: ReviewType
    coach_context: str | None = None
    session_objectives: list[str] = Field(default_factory=list)
    requested_focus_areas: list[str] = Field(default_factory=list)
    manual_observations: list[str] = Field(default_factory=list)
    transcript: str | None = None
    frame_observations: list[dict[str, Any]] = Field(default_factory=list)


class DraftUpdate(BaseModel):
    summary: str = Field(min_length=1)
    observations: list[Observation]
    strengths: list[Strength]
    improvement_areas: list[ImprovementArea]
    recommended_drills: list[RecommendedDrill]
    coach_notes: str | None = None


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ReviewResultRead(GeneratedReview):
    model_config = ConfigDict(from_attributes=True)


class RevisionRead(DraftUpdate):
    id: UUID
    revision_number: int
    edited_by_user_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReviewRead(BaseModel):
    id: UUID
    athlete_id: UUID
    practice_session_id: UUID
    video_id: UUID
    status: ReviewStatus
    review_type: ReviewType
    coach_context: str | None
    prompt_version: str
    generation_started_at: datetime | None
    generation_completed_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
    result: ReviewResultRead | None = None
    latest_revision: RevisionRead | None = None
    model_config = ConfigDict(from_attributes=True)


class ReviewAccepted(BaseModel):
    review_id: UUID
    status: ReviewStatus
    created_at: datetime
    status_url: str


class ReviewStatusRead(BaseModel):
    review_id: UUID
    status: ReviewStatus
    generation_started_at: datetime | None
    generation_completed_at: datetime | None
    retryable: bool
    failure_reason: str | None
