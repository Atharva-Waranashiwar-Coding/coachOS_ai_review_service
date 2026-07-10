from typing import Literal

from pydantic import BaseModel, Field


class Observation(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: Literal[
        "technique", "consistency", "effort", "decision_making", "mobility", "strength", "safety", "other"
    ]
    priority: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0, le=1)
    evidence: str | None = None


class Strength(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ImprovementArea(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: Literal["low", "medium", "high"]


class RecommendedDrill(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    frequency: str | None = None
    difficulty: Literal["beginner", "intermediate", "advanced"]
    safety_note: str | None = None


class GeneratedReview(BaseModel):
    summary: str = Field(min_length=1)
    observations: list[Observation]
    strengths: list[Strength]
    improvement_areas: list[ImprovementArea]
    recommended_drills: list[RecommendedDrill]
    limitations: list[str]
