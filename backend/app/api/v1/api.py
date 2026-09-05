"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import chat, health

api_router = APIRouter()
api_router.include_router(health.router, prefix="", tags=["Health"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
