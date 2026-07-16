from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import validate_token
from app.schemas.review import CurrentUser

bearer = HTTPBearer(auto_error=False)


def token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if not credentials:
        raise UnauthorizedError("Bearer authentication is required.")
    return credentials.credentials


def get_current_user(value: str = Depends(token)) -> CurrentUser:
    return CurrentUser(**validate_token(value))


def require_coach(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "coach":
        raise ForbiddenError("Coach role is required.")
    return user


def require_athlete(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "athlete":
        raise ForbiddenError("Athlete role is required.")
    return user
