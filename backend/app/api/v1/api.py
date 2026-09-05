"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    billing,
    byok,
    chat,
    devops,
    gateway,
    health,
    rag,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="", tags=["Health"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(rag.router, prefix="/rag", tags=["RAG"])
api_router.include_router(byok.router, prefix="/byok", tags=["BYOK"])
api_router.include_router(devops.router, prefix="/devops", tags=["DevOps Bot"])
api_router.include_router(gateway.router, prefix="/gateway", tags=["AI Gateway"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
