"""Authentication for bounded Athlete Service insight aggregation calls."""

import hmac
from dataclasses import dataclass

from fastapi import Header

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


@dataclass(frozen=True)
class InternalServiceIdentity:
    name: str


def require_insight_service(
    service_name: str | None = Header(default=None, alias="X-Service-Name"),
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> InternalServiceIdentity:
    expected = settings.insight_internal_service_token or settings.internal_service_token
    if (
        service_name != "athlete-service"
        or not service_token
        or not expected
        or not hmac.compare_digest(service_token, expected)
    ):
        raise UnauthorizedError("Valid Athlete Service credentials are required.")
    return InternalServiceIdentity(name=service_name)
