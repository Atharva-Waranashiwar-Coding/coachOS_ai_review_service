"""Dependencies for athlete identity resolution across service boundaries."""

from fastapi import Depends

from app.dependencies.auth import require_athlete, token
from app.integrations.athlete_service import AthleteIdentity, AthleteServiceClient
from app.schemas.review import CurrentUser


def get_current_athlete_identity(
    _: CurrentUser = Depends(require_athlete),
    bearer_token: str = Depends(token),
) -> AthleteIdentity:
    return AthleteServiceClient().resolve_current_athlete(bearer_token)
