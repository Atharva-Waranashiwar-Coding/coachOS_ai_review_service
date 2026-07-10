from typing import Any
from uuid import UUID

import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


def validate_token(token: str) -> dict[str, Any]:
    try:
        p = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return {"id": UUID(str(p.get("sub") or p.get("user_id"))), "email": p["email"], "role": p["role"]}
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc
