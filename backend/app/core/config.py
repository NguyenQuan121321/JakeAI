"""Application configuration settings using Pydantic Settings."""

import json
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime settings and environment variables."""

    # Project Information
    PROJECT_NAME: str = "JakeAI Platform"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = (
        "Enterprise-grade embedded AI platform integrating with FinnApiGo "
        "as upstream Identity, Authorization, and Business Core."
    )
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security & CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # FinnApiGo JWT & Identity Provider Integration
    FINNAPIGO_JWKS_URL: str = "http://localhost:8080/.well-known/jwks.json"
    JWT_ALGORITHM: str = "RS256"
    JWT_SECRET_KEY: str = "insecure-development-secret-change-in-production"
    JWT_AUDIENCE: str = "jakeai-service"
    JWT_ISSUER: str = "finnapigo-identity-provider"

    # State, Caching & Vector Database
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None

    # Model Provider API Keys
    GEMINI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # Tier 5: Provider Prompt Caching Feature Flag
    PROVIDER_PROMPT_CACHE_ENABLED: bool = True

    # Commercial SaaS & Security Settings
    BYOK_MASTER_KEY: str = "jakeai-enterprise-master-encryption-key-32b"
    PAYOS_API_KEY: str | None = None
    PAYOS_CHECKSUM_KEY: str = "dev-payos-checksum-secret-key-32b"
    INTERNAL_GATEWAY_SECRET: str = "jakeai-finnapigo-shared-internal-secret-32b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        """Validate and parse CORS origins from string, JSON array, or list."""
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item) for item in parsed]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(item) for item in v]
        return []


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()
