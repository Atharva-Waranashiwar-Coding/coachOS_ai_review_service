from fastapi import APIRouter

from app.api.v1.endpoints.athlete_feedback import router as athlete_feedback
from app.api.v1.endpoints.reviews import router as reviews

api_router = APIRouter()
api_router.include_router(athlete_feedback)
api_router.include_router(reviews)
