from typing import Any, Protocol

from app.ai.schemas import GeneratedReview


class AIProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_review(self, context: dict[str, Any]) -> GeneratedReview: ...
