"""Application configuration settings using Pydantic Settings."""

import hashlib
import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
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
    JWT_SECRET_KEY: str = Field(default="", repr=False, exclude=True)
    JWT_SECRET_PREVIOUS: str | None = Field(default=None, repr=False, exclude=True)
    JWT_AUDIENCE: str = "jakeai-service"
    JWT_ISSUER: str = "finnapigo-identity-provider"

    # State, Caching & Vector Database
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None

    # Context & Data Management (RAG) Settings
    EMBEDDING_PROVIDER: str = "fastembed"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_VERSION: str = "v1.0"
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    BM25_STORAGE_PATH: str = "data/bm25_index.json"

    # Model Provider API Keys
    GEMINI_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    OPENAI_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    ANTHROPIC_API_KEY: str | None = Field(default=None, repr=False, exclude=True)

    # Tier 5: Provider Prompt Caching Feature Flag
    PROVIDER_PROMPT_CACHE_ENABLED: bool = True

    # COST-12: Local Model Provider & Cost Routing Settings
    LOCAL_MODEL_ENDPOINT: str = "http://localhost:11434/v1"
    LOCAL_MODEL_NAME: str = "local-model"
    LOCAL_MODEL_CONTEXT_LIMIT: int = 32_768
    LOCAL_MODEL_TIMEOUT_SECONDS: float = 30.0
    LOCAL_MODEL_CONCURRENCY_LIMIT: int = 4
    LOCAL_MODEL_INPUT_PRICING: float = 0.10
    LOCAL_MODEL_OUTPUT_PRICING: float = 0.20
    LOCAL_MODEL_ENABLED: bool = True
    COST_AWARE_ROUTING_ENABLED: bool = True

    # Commercial SaaS & Security Settings
    BYOK_MASTER_KEY: str = Field(default="", repr=False, exclude=True)
    BYOK_MASTER_KEY_ID: str = ""
    BYOK_PREVIOUS_KEYS: dict[str, str] = Field(
        default_factory=dict, repr=False, exclude=True
    )
    BYOK_RETIRED_KEY_IDS: list[str] = []
    BYOK_RETIRED_KEY_HASHES: list[str] = []
    BYOK_STORAGE_BACKEND: str = "redis"
    BYOK_REDIS_URL: str = Field(default="", repr=False, exclude=True)
    FINNAPIGO_SERVICE_SECRET: str = Field(default="", repr=False, exclude=True)
    AUDIT_HMAC_KEY: str = Field(default="", repr=False, exclude=True)
    PAYOS_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    PAYOS_CHECKSUM_KEY: str = Field(default="", repr=False, exclude=True)
    INTERNAL_GATEWAY_SECRET: str = Field(default="", repr=False, exclude=True)

    # Phase 07: Production Hardening, Timeouts & Safety Limits
    STREAM_TIMEOUT_SECONDS: float = 120.0
    PROVIDER_TIMEOUT_SECONDS: float = 30.0
    HTTP_CLIENT_TIMEOUT_SECONDS: float = 15.0
    MAX_REQUEST_BODY_BYTES: int = 10_485_760  # 10 MB payload ceiling
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 0.5
    REDIS_COOLDOWN_SECONDS: float = 5.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        from app.core.secret_material import (
            decode_secret,
            signing_key_is_retired,
            validate_key_id,
        )

        for key in (self.JWT_SECRET_KEY, self.JWT_SECRET_PREVIOUS):
            if key and signing_key_is_retired(key):
                raise ValueError(
                    "Published signing key is retired in every environment"
                )
        if self.BYOK_STORAGE_BACKEND not in {"redis", "memory"}:
            raise ValueError("Unsupported BYOK storage backend")
        if self.ENVIRONMENT.lower() != "production":
            return self
        try:
            material = [
                decode_secret(value, encoding="hex")
                for value in (
                    self.JWT_SECRET_KEY,
                    self.INTERNAL_GATEWAY_SECRET,
                    self.FINNAPIGO_SERVICE_SECRET,
                    self.AUDIT_HMAC_KEY,
                )
            ]
            if self.JWT_SECRET_PREVIOUS:
                material.append(decode_secret(self.JWT_SECRET_PREVIOUS, encoding="hex"))
            material.append(decode_secret(self.BYOK_MASTER_KEY, encoding="base64"))
            validate_key_id(self.BYOK_MASTER_KEY_ID)
            if self.BYOK_MASTER_KEY_ID in self.BYOK_RETIRED_KEY_IDS:
                raise ValueError
            for kid, key in self.BYOK_PREVIOUS_KEYS.items():
                validate_key_id(kid)
                if kid == self.BYOK_MASTER_KEY_ID or kid in self.BYOK_RETIRED_KEY_IDS:
                    raise ValueError
                material.append(decode_secret(key, encoding="base64"))
            if any(
                hashlib.sha256(key).hexdigest() in self.BYOK_RETIRED_KEY_HASHES
                for key in material
            ):
                raise ValueError
            if self.PAYOS_API_KEY:
                material.append(decode_secret(self.PAYOS_CHECKSUM_KEY, encoding="hex"))
            if len(set(material)) != len(material):
                raise ValueError
            if self.BYOK_STORAGE_BACKEND != "redis" or not self.BYOK_REDIS_URL:
                raise ValueError
        except ValueError:
            raise ValueError(
                "Production secrets require distinct provisioned signing/internal/service/audit/encryption material, key IDs and dedicated Redis"
            ) from None
        return self

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
