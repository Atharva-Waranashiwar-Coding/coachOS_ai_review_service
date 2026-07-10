"""OpenAI implementation of the provider boundary."""

import json
from typing import Any

from app.ai.prompt_templates import SYSTEM_PROMPT
from app.ai.schemas import GeneratedReview
from app.core.config import settings


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self) -> None:
        self.model_name = settings.openai_model

    def generate_review(self, context: dict[str, Any]) -> GeneratedReview:
        if not settings.openai_api_key:
            raise RuntimeError("AI provider is not configured")

        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=settings.ai_request_timeout_seconds)
        response = client.beta.chat.completions.parse(
            model=self.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, default=str)},
            ],
            response_format=GeneratedReview,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_output_tokens,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("AI provider returned no structured review")
        return parsed
