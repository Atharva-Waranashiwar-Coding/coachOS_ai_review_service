"""Resolve the authenticated athlete through the Athlete Service API."""

from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.exceptions import NotFoundError, UpstreamServiceError


class AthleteIdentity(BaseModel):
    id: UUID


class AthleteServiceClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=settings.upstream_timeout_seconds)

    def resolve_current_athlete(self, bearer_token: str) -> AthleteIdentity:
        try:
            response = self.client.get(
                f"{settings.athlete_service_url.rstrip('/')}/api/v1/athlete/me",
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError("Athlete Service is unavailable.") from exc
        if response.status_code in {401, 403, 404}:
            raise NotFoundError("Athlete profile is unavailable.")
        if response.status_code != 200:
            raise UpstreamServiceError("Athlete Service could not resolve athlete identity.")
        try:
            return AthleteIdentity.model_validate(response.json())
        except ValidationError as exc:
            raise UpstreamServiceError("Athlete Service returned an invalid identity contract.") from exc
