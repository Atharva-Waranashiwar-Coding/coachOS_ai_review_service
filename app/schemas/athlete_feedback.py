"""Dedicated athlete-safe approved feedback contracts."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.review import ReviewType


class AthleteObservation(BaseModel):
    title: str
    description: str
    category: str
    priority: Literal["low", "medium", "high"]
    coach_verified: bool = False


class AthleteStrength(BaseModel):
    title: str
    description: str


class AthleteImprovementArea(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high"]


class AthleteRecommendedDrill(BaseModel):
    name: str
    description: str
    reason: str
    frequency: str | None = None
    difficulty: Literal["beginner", "intermediate", "advanced"]
    safety_note: str | None = None


class AthleteSessionContext(BaseModel):
    title: str | None = None
    session_type: str | None = None
    session_date: date | None = None
    location: str | None = None


class AthleteFeedbackSummary(BaseModel):
    review_id: UUID
    review_type: ReviewType
    athlete_message: str | None
    summary_excerpt: str
    approved_at: datetime
    session_context: AthleteSessionContext | None = None


class AthleteFeedbackDetail(BaseModel):
    review_id: UUID
    review_type: ReviewType
    summary: str
    observations: list[AthleteObservation] = Field(default_factory=list)
    strengths: list[AthleteStrength] = Field(default_factory=list)
    improvement_areas: list[AthleteImprovementArea] = Field(default_factory=list)
    recommended_drills: list[AthleteRecommendedDrill] = Field(default_factory=list)
    athlete_message: str | None
    approved_at: datetime
    session_context: AthleteSessionContext | None = None


class AthleteFeedbackPage(BaseModel):
    items: list[AthleteFeedbackSummary]
    page: int
    page_size: int
    total: int
    total_pages: int
