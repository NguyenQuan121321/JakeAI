"""Bring Your Own Key (BYOK) Manager with AES-256-GCM Authenticated Encryption.

Enables tenants to supply their own LLM provider API keys (OpenAI, Gemini, Anthropic, OpenRouter).
Protects against financial token surges and rate-limit depletion.
Keys are encrypted at rest using AES-256-GCM with tenant-isolated key derivation and
decrypted transiently in memory only during active execution.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {"openai", "gemini", "anthropic", "openrouter"}


class BYOKManager:
    """Manages tenant API key encryption, storage, and dynamic in-memory injection."""

    def __init__(self, master_key: str | None = None) -> None:
        settings = get_settings()
        raw_key = master_key or settings.BYOK_MASTER_KEY
        # Ensure 32-byte master key via SHA-256 hash
        self._master_secret = hashlib.sha256(raw_key.encode("utf-8")).digest()
        # In-memory storage fallback when Redis is offline
        self._memory_store: dict[str, dict[str, str]] = {}
        self.redis_client: Any | None = None
        self._redis_available = True

    def _derive_tenant_aesgcm(self, tenant_id: str) -> AESGCM:
        """Derive an isolated 32-byte AES-256-GCM key per tenant using HMAC-SHA256."""
        tenant_key = hashlib.sha256(
            self._master_secret + tenant_id.encode("utf-8")
        ).digest()
        return AESGCM(tenant_key)

    def encrypt_key(self, api_key: str, tenant_id: str) -> str:
        """Encrypt an API key using AES-256-GCM with tenant_id as associated data (AAD).

        Returns:
            Base64 encoded string of (12-byte nonce + ciphertext + 16-byte tag).
        """
        if not api_key:
            raise ValueError("API key cannot be empty")
        if not tenant_id:
            raise ValueError("Tenant ID is required for encryption")

        aesgcm = self._derive_tenant_aesgcm(tenant_id)
        nonce = os.urandom(12)  # Standard 96-bit nonce for GCM
        aad = tenant_id.encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, api_key.encode("utf-8"), aad)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt_key(self, encrypted_payload: str, tenant_id: str) -> str:
        """Decrypt an AES-256-GCM encrypted payload transiently in memory.

        Raises:
            ValueError: If ciphertext is corrupt or tenant_id does not match AAD.
        """
        if not encrypted_payload or not tenant_id:
            raise ValueError("Encrypted payload and tenant ID are required")

        try:
            raw_bytes = base64.b64decode(encrypted_payload.encode("utf-8"))
            if len(raw_bytes) < 28:  # 12 nonce + at least 16 tag
                raise ValueError("Ciphertext payload too short")

            nonce = raw_bytes[:12]
            ciphertext = raw_bytes[12:]
            aesgcm = self._derive_tenant_aesgcm(tenant_id)
            decrypted = aesgcm.decrypt(nonce, ciphertext, tenant_id.encode("utf-8"))
            return decrypted.decode("utf-8")
        except (InvalidTag, Exception) as exc:
            logger.warning("Decryption failed for tenant %s: %s", tenant_id, exc)
            raise ValueError(
                "Failed to decrypt key: authentication tag mismatch or invalid tenant"
            ) from exc

    @staticmethod
    def mask_key(api_key: str) -> str:
        """Return masked key preview preserving provider prefix and last 4 characters."""
        if not api_key:
            return ""
        if len(api_key) <= 8:
            return "sk-***"
        prefix = api_key[:3] if api_key.startswith("sk-") else api_key[:2]
        return f"{prefix}...{api_key[-4:]}"

    async def _get_redis(self) -> Any | None:
        """Lazily initialize Redis connection with fast ping check."""
        if self.redis_client is not None:
            return self.redis_client
        if not self._redis_available:
            return None
        try:
            from redis import asyncio as aioredis

            settings = get_settings()
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            await client.ping()
            self.redis_client = client
            return self.redis_client
        except Exception:
            self._redis_available = False
            return None

    async def store_key(
        self, tenant_id: str, provider: str, api_key: str
    ) -> dict[str, Any]:
        """Encrypt and persist tenant API key for a specified provider."""
        norm_provider = provider.lower().strip()
        if norm_provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}"
            )

        encrypted = self.encrypt_key(api_key, tenant_id)
        redis = await self._get_redis()
        if redis is not None:
            try:
                key_name = f"byok:{tenant_id}:{norm_provider}"
                await redis.set(key_name, encrypted)
            except Exception as exc:
                logger.warning("Redis store failed (%s), using memory", exc)
                self._memory_store.setdefault(tenant_id, {})[norm_provider] = encrypted
        else:
            self._memory_store.setdefault(tenant_id, {})[norm_provider] = encrypted

        return {
            "tenant_id": tenant_id,
            "provider": norm_provider,
            "masked_key": self.mask_key(api_key),
            "status": "configured",
        }

    async def get_decrypted_key(self, tenant_id: str, provider: str) -> str | None:
        """Retrieve and decrypt an API key transiently in memory for inference."""
        norm_provider = provider.lower().strip()
        encrypted_val: str | None = None

        redis = await self._get_redis()
        if redis is not None:
            try:
                key_name = f"byok:{tenant_id}:{norm_provider}"
                encrypted_val = await redis.get(key_name)
            except Exception as exc:
                logger.warning("Redis read failed (%s), checking memory", exc)
                encrypted_val = self._memory_store.get(tenant_id, {}).get(norm_provider)
        else:
            encrypted_val = self._memory_store.get(tenant_id, {}).get(norm_provider)

        if not encrypted_val:
            return None

        return self.decrypt_key(encrypted_val, tenant_id)

    async def list_keys(self, tenant_id: str) -> list[dict[str, Any]]:
        """List all configured providers for a tenant with masked previews."""
        results: list[dict[str, Any]] = []
        redis = await self._get_redis()

        for provider in sorted(SUPPORTED_PROVIDERS):
            encrypted_val: str | None = None
            if redis is not None:
                try:
                    key_name = f"byok:{tenant_id}:{provider}"
                    encrypted_val = await redis.get(key_name)
                except Exception:
                    encrypted_val = self._memory_store.get(tenant_id, {}).get(provider)
            else:
                encrypted_val = self._memory_store.get(tenant_id, {}).get(provider)

            if encrypted_val:
                try:
                    decrypted = self.decrypt_key(encrypted_val, tenant_id)
                    masked = self.mask_key(decrypted)
                    results.append(
                        {
                            "provider": provider,
                            "masked_key": masked,
                            "configured": True,
                        }
                    )
                except Exception:
                    results.append(
                        {
                            "provider": provider,
                            "masked_key": "sk-corrupt",
                            "configured": False,
                        }
                    )
            else:
                results.append(
                    {
                        "provider": provider,
                        "masked_key": None,
                        "configured": False,
                    }
                )
        return results

    async def delete_key(self, tenant_id: str, provider: str) -> bool:
        """Revoke and delete a provider key for a tenant."""
        norm_provider = provider.lower().strip()
        deleted = False
        redis = await self._get_redis()
        if redis is not None:
            try:
                key_name = f"byok:{tenant_id}:{norm_provider}"
                del_count = await redis.delete(key_name)
                deleted = bool(del_count > 0)
            except Exception as exc:
                logger.debug("Redis delete skipped (%s)", exc)

        if (
            tenant_id in self._memory_store
            and norm_provider in self._memory_store[tenant_id]
        ):
            del self._memory_store[tenant_id][norm_provider]
            deleted = True

        return deleted


_byok_manager: BYOKManager | None = None


def get_byok_manager() -> BYOKManager:
    """Singleton getter for BYOKManager."""
    global _byok_manager
    if _byok_manager is None:
        _byok_manager = BYOKManager()
    return _byok_manager
