"""Authenticated BYOK custody, CAS lifecycle and resumable encryption rotation.

Masters are provisioned separately from ciphertext. Python memory erasure and
protection from a compromised application process are not promised.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.byok_storage import BYOKError, MemoryStore, RedisStore
from app.core.config import get_settings
from app.core.credential_redaction import protect_credential
from app.core.secret_material import decode_secret, validate_key_id

SUPPORTED_PROVIDERS = {
    "openai",
    "gemini",
    "anthropic",
    "groq",
    "deepseek",
    "openrouter",
}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class BYOKManager:
    """One credential slot per tenant/provider, owned by its initial trusted writer."""

    def __init__(
        self,
        master_key: str | None = None,
        *,
        key_id: str | None = None,
        previous_keys: dict[str, str] | None = None,
        retired_key_ids: list[str] | None = None,
        retired_key_hashes: list[str] | None = None,
        store: MemoryStore | RedisStore | None = None,
    ) -> None:
        settings = get_settings()
        try:
            self.key_id = validate_key_id(
                key_id if key_id is not None else settings.BYOK_MASTER_KEY_ID
            )
            self.retired = frozenset(
                retired_key_ids
                if retired_key_ids is not None
                else settings.BYOK_RETIRED_KEY_IDS
            )
            previous = (
                previous_keys
                if previous_keys is not None
                else settings.BYOK_PREVIOUS_KEYS
            )
            if self.key_id in previous or self.key_id in self.retired:
                raise ValueError
            self._keys = {
                self.key_id: decode_secret(
                    master_key if master_key is not None else settings.BYOK_MASTER_KEY,
                    encoding="base64",
                )
            }
            for kid, value in previous.items():
                validate_key_id(kid)
                if kid in self.retired:
                    raise ValueError
                self._keys[kid] = decode_secret(value, encoding="base64")
            if len(set(self._keys.values())) != len(self._keys):
                raise ValueError
            retired_hashes = (
                retired_key_hashes
                if retired_key_hashes is not None
                else settings.BYOK_RETIRED_KEY_HASHES
            )
            if any(
                hashlib.sha256(key).hexdigest() in retired_hashes
                for key in self._keys.values()
            ):
                raise ValueError
        except ValueError:
            raise BYOKError("BYOK_KEY_UNAVAILABLE") from None
        if settings.ENVIRONMENT.lower() == "production" and isinstance(
            store, MemoryStore
        ):
            raise BYOKError("BYOK_STORAGE_UNAVAILABLE")
        self.store = (
            store
            if store is not None
            else (
                MemoryStore()
                if settings.BYOK_STORAGE_BACKEND == "memory"
                else RedisStore(settings.BYOK_REDIS_URL or settings.REDIS_URL)
            )
        )

    @staticmethod
    def _provider(provider: str) -> str:
        norm = provider.lower().strip()
        if norm not in SUPPORTED_PROVIDERS:
            raise BYOKError("BYOK_UNSUPPORTED_PROVIDER", 400)
        return norm

    @staticmethod
    def _storage_key(tenant_id: str, provider: str) -> str:
        if not tenant_id:
            raise BYOKError("BYOK_IDENTITY_REQUIRED", 403)
        return f"byok:v1:{hashlib.sha256(tenant_id.encode()).hexdigest()}:{provider}"

    def _key(self, kid: str) -> bytes:
        if kid in self.retired:
            raise BYOKError("BYOK_KEY_RETIRED")
        if kid not in self._keys:
            raise BYOKError("BYOK_KEY_UNKNOWN")
        return self._keys[kid]

    def _seal(
        self, record: dict[str, Any], tenant_id: str, provider: str, revision: int
    ) -> str:
        header = {
            "version": 1,
            "kid": self.key_id,
            "tenant": tenant_id,
            "provider": provider,
            "revision": revision,
        }
        nonce = os.urandom(12)
        encrypted = AESGCM(self._key(self.key_id)).encrypt(
            nonce, _json(record).encode(), _json(header).encode()
        )
        return _json(
            {**header, "payload": base64.b64encode(nonce + encrypted).decode()}
        )

    def _open(
        self, raw: str, tenant_id: str, provider: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict) or "version" not in envelope:
                raise BYOKError("BYOK_LEGACY_RECORD", 409)
            if envelope["version"] != 1 or type(envelope["version"]) is not int:
                raise BYOKError("BYOK_RECORD_VERSION", 409)
            if set(envelope) != {
                "version",
                "kid",
                "tenant",
                "provider",
                "revision",
                "payload",
            }:
                raise ValueError
            if envelope["tenant"] != tenant_id or envelope["provider"] != provider:
                raise ValueError
            if type(envelope["revision"]) is not int or envelope["revision"] < 1:
                raise ValueError
            key = self._key(envelope["kid"])
            payload = base64.b64decode(envelope["payload"], validate=True)
            header = {k: v for k, v in envelope.items() if k != "payload"}
            record = json.loads(
                AESGCM(key).decrypt(payload[:12], payload[12:], _json(header).encode())
            )
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("api_key"), str)
                or not isinstance(record.get("owner_id"), str)
            ):
                raise ValueError
            if record.get("status") not in {"active", "revoked"}:
                raise ValueError
            return record, envelope
        except BYOKError:
            raise
        except Exception:
            raise BYOKError("BYOK_RECORD_CORRUPT", 409) from None

    def encrypt_key(
        self, api_key: str, tenant_id: str, provider: str = "openai"
    ) -> str:
        if not api_key:
            raise BYOKError("BYOK_INVALID_KEY", 400)
        norm = self._provider(provider)
        self._storage_key(tenant_id, norm)
        return self._seal(
            {"api_key": api_key, "owner_id": "", "status": "active"}, tenant_id, norm, 1
        )

    def decrypt_key(
        self, encrypted_payload: str, tenant_id: str, provider: str = "openai"
    ) -> str:
        record, _ = self._open(encrypted_payload, tenant_id, self._provider(provider))
        return protect_credential(str(record["api_key"]))

    @staticmethod
    def mask_key(api_key: str) -> str:
        # Constant preview also protects short values and provider-prefix canaries.
        return "********" if api_key else ""

    async def check_storage(self) -> None:
        if isinstance(self.store, RedisStore):
            await self.store.check(
                durable=get_settings().ENVIRONMENT.lower() == "production"
            )

    async def _get_raw_val(self, tenant_id: str, provider: str) -> str | None:
        norm = self._provider(provider)
        raw = await self.store.get(self._storage_key(tenant_id, norm))
        if raw is None and await self.store.get(f"byok:{tenant_id}:{norm}") is not None:
            raise BYOKError("BYOK_LEGACY_RECORD", 409)
        return raw

    async def _save_raw_val(self, tenant_id: str, provider: str, packed: str) -> None:
        """Test/import seam; ordinary lifecycle compares its observed revision."""
        key = self._storage_key(tenant_id, self._provider(provider))
        prior = await self.store.get(key)
        if not await self.store.cas(key, prior, packed):
            raise BYOKError("BYOK_CONFLICT", 409)

    @staticmethod
    def _authorize(
        record: dict[str, Any], actor_id: str | None, delegated_admin: bool
    ) -> None:
        if (
            actor_id is not None
            and actor_id != record["owner_id"]
            and not delegated_admin
        ):
            raise BYOKError("BYOK_OWNER_REQUIRED", 403)

    async def _load(
        self, tenant: str, provider: str, actor: str | None, delegated: bool
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        raw = await self._get_raw_val(tenant, provider)
        if raw is None:
            raise BYOKError("BYOK_NOT_CONFIGURED", 404)
        record, envelope = self._open(raw, tenant, provider)
        self._authorize(record, actor, delegated)
        return raw, record, envelope

    async def _commit(
        self,
        tenant: str,
        provider: str,
        prior: str | None,
        record: dict[str, Any] | None,
        revision: int,
    ) -> None:
        value = (
            self._seal(record, tenant, provider, revision)
            if record is not None
            else None
        )
        if not await self.store.cas(self._storage_key(tenant, provider), prior, value):
            raise BYOKError("BYOK_CONFLICT", 409)

    def _public(
        self, tenant: str, provider: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "tenant_id": tenant,
            "provider": provider,
            "masked_key": self.mask_key(record["api_key"]),
            "status": "configured" if record["status"] == "active" else "revoked",
            **{
                k: record.get(k)
                for k in (
                    "created_at",
                    "updated_at",
                    "last_validated_at",
                    "validation_status",
                )
            },
        }

    async def validate_key(
        self, provider: str, api_key: str
    ) -> tuple[bool, str | None]:
        norm = self._provider(provider)
        clean = api_key.strip()
        if len(clean) < 8 or len(clean) > 4096:
            return False, "BYOK_INVALID_KEY"
        endpoints = {
            "openai": "https://api.openai.com/v1/models",
            "anthropic": "https://api.anthropic.com/v1/models",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
            "groq": "https://api.groq.com/openai/v1/models",
            "deepseek": "https://api.deepseek.com/models",
            "openrouter": "https://openrouter.ai/api/v1/auth/key",
        }
        headers = {"Authorization": f"Bearer {clean}"}
        if norm == "anthropic":
            headers = {"x-api-key": clean, "anthropic-version": "2023-06-01"}
        elif norm == "gemini":
            headers = {"x-goog-api-key": clean}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(endpoints[norm], headers=headers)
            if response.status_code == 200:
                return True, None
            if response.status_code in {401, 403}:
                return False, "BYOK_PROVIDER_REJECTED"
            return False, "BYOK_PROVIDER_UNAVAILABLE"
        except Exception:
            # No URLs, exception text or provider response bodies in diagnostics.
            return False, "BYOK_PROVIDER_UNAVAILABLE"

    async def _validate(self, provider: str, key: str, enabled: bool) -> dict[str, Any]:
        if not enabled:
            return {"last_validated_at": None, "validation_status": "untested"}
        valid, error = await self.validate_key(provider, key)
        if not valid:
            raise BYOKError(
                error or "BYOK_PROVIDER_REJECTED",
                503 if error == "BYOK_PROVIDER_UNAVAILABLE" else 400,
            )
        return {
            "last_validated_at": datetime.now(UTC).isoformat(),
            "validation_status": "valid",
        }

    async def store_key(
        self,
        tenant_id: str,
        provider: str,
        api_key: str,
        validate: bool = False,
        *,
        actor_id: str | None = None,
        delegated_admin: bool = False,
    ) -> dict[str, Any]:
        norm = self._provider(provider)
        clean = api_key.strip()
        if not 8 <= len(clean) <= 4096:
            raise BYOKError("BYOK_INVALID_KEY", 400)
        prior = await self._get_raw_val(tenant_id, norm)
        existing: dict[str, Any] = {}
        revision = 1
        if prior is not None:
            existing, envelope = self._open(prior, tenant_id, norm)
            self._authorize(existing, actor_id, delegated_admin)
            revision = envelope["revision"] + 1
        validation = await self._validate(norm, clean, validate)
        now = datetime.now(UTC).isoformat()
        record = {
            "api_key": clean,
            "owner_id": existing.get("owner_id", actor_id or ""),
            "status": "active",
            "created_at": existing.get("created_at", now),
            "updated_at": now,
            **validation,
        }
        await self._commit(tenant_id, norm, prior, record, revision)
        return self._public(tenant_id, norm, record)

    async def rotate_key(
        self,
        tenant_id: str,
        provider: str,
        new_api_key: str,
        validate: bool = False,
        *,
        actor_id: str | None = None,
        delegated_admin: bool = False,
    ) -> dict[str, Any]:
        norm = self._provider(provider)
        prior, record, envelope = await self._load(
            tenant_id, norm, actor_id, delegated_admin
        )
        clean = new_api_key.strip()
        if not 8 <= len(clean) <= 4096:
            raise BYOKError("BYOK_INVALID_KEY", 400)
        validation = await self._validate(norm, clean, validate)
        record.update(
            api_key=clean,
            status="active",
            updated_at=datetime.now(UTC).isoformat(),
            **validation,
        )
        await self._commit(tenant_id, norm, prior, record, envelope["revision"] + 1)
        return self._public(tenant_id, norm, record)

    async def validate_stored_key(
        self,
        tenant_id: str,
        provider: str,
        *,
        actor_id: str | None = None,
        delegated_admin: bool = False,
    ) -> tuple[bool, str | None]:
        norm = self._provider(provider)
        prior, record, envelope = await self._load(
            tenant_id, norm, actor_id, delegated_admin
        )
        if record["status"] != "active":
            raise BYOKError("BYOK_REVOKED", 409)
        valid, error = await self.validate_key(norm, record["api_key"])
        record.update(
            last_validated_at=datetime.now(UTC).isoformat(),
            validation_status="valid"
            if valid
            else "unavailable"
            if error == "BYOK_PROVIDER_UNAVAILABLE"
            else "invalid",
        )
        await self._commit(tenant_id, norm, prior, record, envelope["revision"] + 1)
        return valid, error

    async def revoke_key(
        self,
        tenant_id: str,
        provider: str,
        *,
        actor_id: str | None = None,
        delegated_admin: bool = False,
    ) -> dict[str, Any]:
        norm = self._provider(provider)
        prior, record, envelope = await self._load(
            tenant_id, norm, actor_id, delegated_admin
        )
        record.update(status="revoked", updated_at=datetime.now(UTC).isoformat())
        await self._commit(tenant_id, norm, prior, record, envelope["revision"] + 1)
        return self._public(tenant_id, norm, record)

    async def get_decrypted_key(self, tenant_id: str, provider: str) -> str | None:
        norm = self._provider(provider)
        raw = await self._get_raw_val(tenant_id, norm)
        if raw is None:
            return None
        record, _ = self._open(raw, tenant_id, norm)
        if record["status"] != "active":
            raise BYOKError("BYOK_REVOKED", 409)
        return protect_credential(str(record["api_key"]))

    async def list_keys(
        self,
        tenant_id: str,
        *,
        actor_id: str | None = None,
        delegated_admin: bool = False,
    ) -> list[dict[str, Any]]:
        results = []
        for provider in sorted(SUPPORTED_PROVIDERS):
            raw = await self._get_raw_val(tenant_id, provider)
            if raw is None:
                results.append(
                    {
                        "provider": provider,
                        "masked_key": None,
                        "configured": False,
                        "status": "unconfigured",
                    }
                )
                continue
            record, _ = self._open(raw, tenant_id, provider)
            self._authorize(record, actor_id, delegated_admin)
            results.append(
                {
                    **self._public(tenant_id, provider, record),
                    "configured": record["status"] == "active",
                }
            )
        return results

    async def delete_key(
        self,
        tenant_id: str,
        provider: str,
        *,
        actor_id: str | None = None,
        delegated_admin: bool = False,
    ) -> bool:
        norm = self._provider(provider)
        try:
            prior, _, envelope = await self._load(
                tenant_id, norm, actor_id, delegated_admin
            )
        except BYOKError as exc:
            if exc.code == "BYOK_NOT_CONFIGURED":
                return False
            raise
        await self._commit(tenant_id, norm, prior, None, envelope["revision"] + 1)
        return True

    async def reencrypt_batch(
        self, cursor: str = "0", count: int = 100
    ) -> dict[str, Any]:
        """CAS migration; repeat full passes after faults/restart and before retirement."""
        next_cursor, keys = await self.store.scan(cursor, max(1, min(count, 1000)))
        report: dict[str, Any] = {
            "cursor": next_cursor,
            "migrated": 0,
            "current": 0,
            "conflicts": 0,
            "errors": {},
        }
        for key in keys:
            try:
                raw = await self.store.get(key)
                if raw is None:
                    continue
                envelope = json.loads(raw)
                tenant, provider = (
                    envelope["tenant"],
                    self._provider(envelope["provider"]),
                )
                if self._storage_key(tenant, provider) != key:
                    raise BYOKError("BYOK_RECORD_CORRUPT", 409)
                record, envelope = self._open(raw, tenant, provider)
                if envelope["kid"] == self.key_id:
                    report["current"] += 1
                    continue
                replacement = self._seal(
                    record, tenant, provider, envelope["revision"] + 1
                )
                if await self.store.cas(key, raw, replacement):
                    report["migrated"] += 1
                else:
                    report["conflicts"] += 1
            except Exception as exc:
                code = exc.code if isinstance(exc, BYOKError) else "BYOK_RECORD_CORRUPT"
                report["errors"][code] = report["errors"].get(code, 0) + 1
        return report


_byok_manager: BYOKManager | None = None


def get_byok_manager() -> BYOKManager:
    global _byok_manager
    if _byok_manager is None:
        _byok_manager = BYOKManager()
    return _byok_manager
