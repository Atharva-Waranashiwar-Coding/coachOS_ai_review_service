from fastapi import APIRouter

from app.api.v1.endpoints.reviews import router as reviews

api_router = APIRouter()
api_router.include_router(reviews)
