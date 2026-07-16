"""Request and response contracts for the coach-owned review workflow."""

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.schemas import GeneratedReview
from app.core.config import settings
from app.models.review import AuditAction, RejectionCategory, ReviewStatus, ReviewType, ReviewVisibility

_TAG_PATTERN = re.compile(r"<[^>]+>")


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(_TAG_PATTERN.sub("", value).split())


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


class ObservationEdit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=3000)
    category: Literal[
        "technique", "consistency", "effort", "decision_making", "mobility", "strength", "safety", "other"
    ]
    priority: Literal["low", "medium", "high"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: str | None = Field(default=None, max_length=2000)
    coach_verified: bool = False

    @field_validator("title", "description", "evidence", mode="before")
    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        value = clean_text(value)
        if value is not None and not value:
            raise ValueError("value cannot be blank")
        return value


class StrengthEdit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    taxonomy_code: str | None = Field(default=None, max_length=100)

    _normalize = field_validator("title", "description", "taxonomy_code", mode="before")(clean_text)


class ImprovementAreaEdit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    priority: Literal["low", "medium", "high"]
    taxonomy_code: str | None = Field(default=None, max_length=100)

    _normalize = field_validator("title", "description", "taxonomy_code", mode="before")(clean_text)


class RecommendedDrillEdit(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    frequency: str | None = Field(default=None, max_length=200)
    difficulty: Literal["beginner", "intermediate", "advanced"]
    safety_note: str | None = Field(default=None, max_length=1000)

    _normalize = field_validator("name", "description", "reason", "frequency", "safety_note", mode="before")(clean_text)


class ReviewContent(BaseModel):
    summary: str = Field(min_length=1)
    observations: list[ObservationEdit] = Field(default_factory=list)
    strengths: list[StrengthEdit] = Field(default_factory=list)
    improvement_areas: list[ImprovementAreaEdit] = Field(default_factory=list)
    recommended_drills: list[RecommendedDrillEdit] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, value: str) -> str:
        cleaned = clean_text(value)
        if not cleaned:
            raise ValueError("summary cannot be blank")
        if len(cleaned) > settings.max_review_summary_characters:
            raise ValueError("summary exceeds configured limit")
        return cleaned

    @field_validator("observations")
    @classmethod
    def observation_limit(cls, value: list[ObservationEdit]) -> list[ObservationEdit]:
        if len(value) > settings.max_observations_per_review:
            raise ValueError("too many observations")
        return value

    @field_validator("strengths")
    @classmethod
    def strength_limit(cls, value: list[StrengthEdit]) -> list[StrengthEdit]:
        if len(value) > settings.max_strengths_per_review:
            raise ValueError("too many strengths")
        return value

    @field_validator("improvement_areas")
    @classmethod
    def improvement_limit(cls, value: list[ImprovementAreaEdit]) -> list[ImprovementAreaEdit]:
        if len(value) > settings.max_improvement_areas_per_review:
            raise ValueError("too many improvement areas")
        return value

    @field_validator("recommended_drills")
    @classmethod
    def drill_limit(cls, value: list[RecommendedDrillEdit]) -> list[RecommendedDrillEdit]:
        if len(value) > settings.max_recommended_drills_per_review:
            raise ValueError("too many recommended drills")
        return value


class ReviewRevisionCreate(ReviewContent):
    expected_revision_number: int = Field(ge=0)
    coach_notes: str | None = Field(default=None)
    athlete_message: str | None = Field(default=None)
    change_summary: str | None = Field(default=None)

    @field_validator("coach_notes", mode="before")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        cleaned = clean_text(value)
        if cleaned and len(cleaned) > settings.max_coach_notes_characters:
            raise ValueError("coach notes exceed configured limit")
        return cleaned

    @field_validator("athlete_message", mode="before")
    @classmethod
    def clean_message(cls, value: str | None) -> str | None:
        cleaned = clean_text(value)
        if cleaned and len(cleaned) > settings.max_athlete_message_characters:
            raise ValueError("athlete message exceeds configured limit")
        return cleaned

    @field_validator("change_summary", mode="before")
    @classmethod
    def clean_change_summary(cls, value: str | None) -> str | None:
        cleaned = clean_text(value)
        if cleaned and len(cleaned) > settings.max_change_summary_characters:
            raise ValueError("change summary exceeds configured limit")
        return cleaned


class ActiveDraft(ReviewContent):
    source: Literal["generated", "revision"]
    revision_id: UUID | None = None
    revision_number: int = 0
    coach_notes: str | None = None
    athlete_message: str | None = None
    change_summary: str | None = None


class ReviewResultRead(GeneratedReview):
    model_config = ConfigDict(from_attributes=True)


class RevisionRead(ActiveDraft):
    id: UUID
    edited_by_user_id: UUID
    based_on_revision_number: int | None
    created_at: datetime
    source: Literal["revision"] = "revision"
    model_config = ConfigDict(from_attributes=True)


class RevisionListItem(BaseModel):
    id: UUID
    revision_number: int
    edited_by_user_id: UUID
    change_summary: str | None
    based_on_revision_number: int | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RevisionPage(BaseModel):
    items: list[RevisionListItem]
    page: int
    page_size: int
    total: int


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


class ApprovalRequest(BaseModel):
    revision_id: UUID | None = None
    expected_revision_number: int = Field(ge=0)
    visibility: ReviewVisibility = ReviewVisibility.COACH_ONLY
    athlete_message: str | None = None
    confirmation: bool

    _clean_message = field_validator("athlete_message", mode="before")(clean_text)


class RejectionRequest(BaseModel):
    category: RejectionCategory
    reason: str | None = Field(default=None, max_length=3000)
    expected_revision_number: int = Field(ge=0)
    confirmation: bool

    _clean_reason = field_validator("reason", mode="before")(clean_text)


class PreviewRequest(BaseModel):
    revision_id: UUID | None = None
    visibility: ReviewVisibility = ReviewVisibility.ATHLETE_VISIBLE
    athlete_message: str | None = None

    _clean_message = field_validator("athlete_message", mode="before")(clean_text)


class AthletePreview(BaseModel):
    athlete_id: UUID
    review_id: UUID
    summary: str
    observations: list[dict[str, Any]]
    strengths: list[StrengthEdit]
    improvement_areas: list[ImprovementAreaEdit]
    recommended_drills: list[RecommendedDrillEdit]
    athlete_message: str | None
    visibility: ReviewVisibility
    is_preview: bool = True


class ApprovedSnapshotRead(ReviewContent):
    id: UUID
    review_id: UUID
    source_revision_id: UUID | None
    approved_by_user_id: UUID
    athlete_message: str | None
    visibility: ReviewVisibility
    approved_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ApprovedReviewContract(ApprovedSnapshotRead):
    athlete_id: UUID
    status: Literal["approved"] = "approved"


class AuditEventRead(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action_type: AuditAction
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    occurred_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AuditPage(BaseModel):
    items: list[AuditEventRead]
    page: int
    page_size: int
    total: int


class AllowedActions(BaseModel):
    can_edit: bool
    can_preview: bool
    can_approve: bool
    can_reject: bool
    can_retry: bool


class ReviewRead(BaseModel):
    id: UUID
    athlete_id: UUID
    practice_session_id: UUID
    video_id: UUID
    status: ReviewStatus
    review_type: ReviewType
    latest_revision_number: int
    generated_at: datetime | None
    created_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
    result: ReviewResultRead | None = None
    active_draft: ActiveDraft | None = None
    approved_snapshot: ApprovedSnapshotRead | None = None
    rejection_category: RejectionCategory | None = None
    allowed_actions: AllowedActions
    model_config = ConfigDict(from_attributes=True)
