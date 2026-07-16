"""Safe approved-review contracts for deterministic progress aggregation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.models.review import ReviewType, ReviewVisibility


class ReviewInsightStrength(BaseModel):
    title: str
    description: str
    taxonomy_code: str | None = None


class ReviewInsightImprovementArea(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high"]
    taxonomy_code: str | None = None


class ReviewInsightRecommendedDrill(BaseModel):
    name: str
    description: str
    reason: str
    frequency: str | None = None
    difficulty: Literal["beginner", "intermediate", "advanced"]
    safety_note: str | None = None


class ApprovedReviewInsightItem(BaseModel):
    review_id: UUID
    athlete_id: UUID
    review_type: ReviewType
    approved_at: datetime
    visibility: ReviewVisibility
    strengths: list[ReviewInsightStrength] = Field(default_factory=list)
    improvement_areas: list[ReviewInsightImprovementArea] = Field(default_factory=list)
    recommended_drills: list[ReviewInsightRecommendedDrill] = Field(default_factory=list)
    practice_session_id: UUID
    video_id: UUID


class ApprovedReviewInsightPage(BaseModel):
    items: list[ApprovedReviewInsightItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class ReviewInsightBatchRequest(BaseModel):
    athlete_ids: list[UUID] = Field(min_length=1)
    start_date: datetime
    end_date: datetime
    comparison_start: datetime | None = None
    comparison_end: datetime | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> "ReviewInsightBatchRequest":
        if len(set(self.athlete_ids)) != len(self.athlete_ids):
            raise ValueError("athlete_ids must not contain duplicates")
        if len(self.athlete_ids) > settings.insight_max_batch_athletes:
            raise ValueError("athlete_ids exceeds the configured batch limit")
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if (self.comparison_start is None) != (self.comparison_end is None):
            raise ValueError("comparison_start and comparison_end must be provided together")
        if self.comparison_start and self.comparison_end and self.comparison_start >= self.comparison_end:
            raise ValueError("comparison_start must be before comparison_end")
        return self


class ReviewInsightBatchResponse(BaseModel):
    items: list[ApprovedReviewInsightItem]
