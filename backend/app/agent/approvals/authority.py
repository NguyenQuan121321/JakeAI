"""Durable two-person authority for publishing a safe calculator result.

Redis is a dedicated noeviction/AOF-always authority, never the cache. The
single-key Lua transition checks server time and compares the entire record.
The controlled effect is publication of the calculator result in that same
record, atomic with one-time consumption. Pure calculation may repeat; no
external effect, general tool execution or checkpoint resume is authorized.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.byok_storage import BYOKError, RedisStore
from app.core.config import get_settings
from app.core.identity import verify_access
from app.core.identity_state import AuthorityLease, authorize_effect, current_authority
from app.core.secret_material import decode_secret

POLICY_VERSION = "approval-calculator-v1"
TOOL_VERSION = "calculator-v1"
POLICY_KEY = "approval:active-policy"


class SafeApprovalProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    approver_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    expression: str = Field(min_length=1, max_length=128, pattern=r"^[0-9+*/(). %\-]+$")
    expires_in: int = Field(default=300, ge=1, le=300)


class BoundDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    approved: bool
    action_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class BoundConsume(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def binding(claims: Any) -> dict[str, Any]:
    return {k: claims[k] for k in ("tid", "sub", "sid", "pwdver", "auth_epoch")}


class ApprovalAuthority:
    # No write precedes the last check. SET is the sole mutation and stores both
    # consume and result: a reply loss cannot make a retry publish a second effect.
    TRANSITION = """
local now = tonumber(redis.call('TIME')[1])
local policy = redis.call('GET', KEYS[2])
if not policy then return -3 end
if policy ~= ARGV[5] then return -4 end
if now >= tonumber(ARGV[3]) then return -1 end
if now - tonumber(ARGV[4]) > 2 or tonumber(ARGV[4]) > now + 1 then return -2 end
local old = redis.call('GET', KEYS[1])
if (ARGV[1] == '' and old) or (ARGV[1] ~= '' and old ~= ARGV[1]) then return 0 end
redis.call('SET', KEYS[1], ARGV[2])
return 1
"""

    def __init__(self) -> None:
        settings = get_settings()
        try:
            if not settings.APPROVAL_REDIS_URL:
                raise ValueError
            target = urlsplit(settings.APPROVAL_REDIS_URL)
            endpoint = (target.hostname, target.port or 6379)
            if (
                target.scheme not in {"redis", "rediss"}
                or not target.hostname
                or not target.password
            ):
                raise ValueError
            for other in (settings.REDIS_URL, settings.BYOK_REDIS_URL):
                parsed = urlsplit(other)
                if endpoint == (parsed.hostname, parsed.port or 6379):
                    raise ValueError
            key = decode_secret(settings.APPROVAL_CREDENTIAL_KEY, encoding="base64")
            if len(key) != 32:
                raise ValueError
            # Credential custody has its own purpose key, not user signing or BYOK.
            for credential in (
                settings.JWT_SECRET_KEY,
                settings.JWT_SECRET_PREVIOUS,
                settings.BYOK_MASTER_KEY,
                settings.IDENTITY_STATE_SECRET,
            ):
                if credential and key == decode_secret(credential, encoding="base64"):
                    raise ValueError
            self.cipher = AESGCM(key)
            self.store = RedisStore(settings.APPROVAL_REDIS_URL)
        except (ValueError, TypeError):
            raise HTTPException(503, "Approval authority unavailable") from None

    async def close(self) -> None:
        await self.store.client.aclose()

    async def _check_store(self) -> None:
        try:
            await self.store.check(durable=True)
        except BYOKError:
            raise HTTPException(503, "Approval authority unavailable") from None

    async def _policy_epoch(self) -> int:
        await self._check_store()
        try:
            raw = await self.store.get(POLICY_KEY)
            if raw is None:
                raise HTTPException(503, "Approval policy is not provisioned")
            policy = json.loads(raw)
            if (
                set(policy) != {"epoch", "policy", "tool"}
                or type(policy["epoch"]) is not int
                or not 1 <= policy["epoch"] <= 2147483647
                or policy["policy"] != POLICY_VERSION
                or policy["tool"] != TOOL_VERSION
            ):
                raise HTTPException(409, "Approval policy or tool changed")
            return int(policy["epoch"])
        except (BYOKError, ValueError, TypeError, KeyError):
            raise HTTPException(503, "Approval policy unavailable") from None

    @staticmethod
    def _key(tenant: str, approval_id: str) -> str:
        # No user-controlled Redis pattern or path; full namespace is hashed.
        return (
            "approval:v1:"
            + hashlib.sha256(canonical([tenant, approval_id]).encode()).hexdigest()
        )

    async def _read(
        self, tenant: str, task: str, run: str, approval_id: str
    ) -> tuple[str, dict[str, Any]]:
        await self._check_store()
        try:
            raw = await self.store.get(self._key(tenant, approval_id))
            if raw is None:
                raise HTTPException(404, "Not found")
            record = json.loads(raw)
            if (record["tenant_id"], record["task_id"], record["run_id"]) != (
                tenant,
                task,
                run,
            ):
                raise HTTPException(404, "Not found")
            return raw, record
        except (BYOKError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Approval authority unavailable") from None

    @staticmethod
    def _current(permission: str) -> AuthorityLease:
        lease = current_authority.get()
        if lease is None or not lease.operation_permissions:
            raise HTTPException(503, "Fresh bound approval authority required")
        if permission not in lease.claims["perms"]:
            raise HTTPException(403, "Insufficient permissions")
        return lease

    @staticmethod
    def _valid(record: dict[str, Any], action_hash: str) -> None:
        action = record["action"]
        if (
            action["policy_version"] != POLICY_VERSION
            or action["tool_version"] != TOOL_VERSION
        ):
            raise HTTPException(409, "Approval policy or tool changed")
        if (
            record["action_hash"] != action_hash
            or hashlib.sha256(canonical(action).encode()).hexdigest() != action_hash
        ):
            raise HTTPException(409, "Approval action changed")
        if time.time() >= action["expires_at"]:
            raise HTTPException(409, "Approval expired")

    async def _commit(
        self, record: dict[str, Any], prior: str, checked_at: int
    ) -> None:
        await self._check_store()
        try:
            result = await self.store.client.eval(
                self.TRANSITION,
                2,
                self._key(record["tenant_id"], record["approval_id"]),
                POLICY_KEY,
                prior,
                canonical(record),
                record["action"]["expires_at"],
                checked_at,
                canonical(
                    {
                        "epoch": record["action"]["policy_epoch"],
                        "policy": POLICY_VERSION,
                        "tool": TOOL_VERSION,
                    }
                ),
            )
        except Exception:
            # The write may have committed. Retry must read the consumed record;
            # never restore APPROVED after an uncertain acknowledgement.
            raise HTTPException(
                503, "Approval authority unavailable; reconcile status"
            ) from None
        if result == -3:
            raise HTTPException(503, "Approval policy is not provisioned")
        if result != 1:
            raise HTTPException(409, "Approval expired, changed or already used")

    @staticmethod
    def public(record: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in record.items() if not k.startswith("_")}

    async def create(
        self, task: str, run: str, proposal: SafeApprovalProposal
    ) -> dict[str, Any]:
        lease = self._current("agent:execute")
        if proposal.approver_id == lease.claims["sub"]:
            raise HTTPException(403, "Separate approver required")
        policy_epoch = await self._policy_epoch()
        await authorize_effect("agent:execute")
        now = int(time.time())
        action = {
            "tenant_id": lease.claims["tid"],
            "requester_id": lease.claims["sub"],
            "approver_id": proposal.approver_id,
            "task_id": task,
            "run_id": run,
            "tool_name": "calculator",
            "tool_version": TOOL_VERSION,
            "policy_version": POLICY_VERSION,
            "policy_epoch": policy_epoch,
            "arguments": {"expression": proposal.expression},
            "expires_at": min(now + proposal.expires_in, lease.claims["exp"]),
        }
        record = {
            "approval_id": "appr_" + uuid.uuid4().hex,
            "tenant_id": action["tenant_id"],
            "task_id": task,
            "run_id": run,
            "action": action,
            "action_hash": hashlib.sha256(canonical(action).encode()).hexdigest(),
            "status": "pending",
            "created_at": now,
            "requester": binding(lease.claims),
            "approver": None,
            "result": None,
            "consumed_at": None,
        }
        await self._commit(record, "", now)
        return self.public(record)

    async def get(
        self, tenant: str, task: str, run: str, approval_id: str
    ) -> dict[str, Any]:
        _, record = await self._read(tenant, task, run, approval_id)
        lease = self._current("agent:read")
        if lease.claims["sub"] not in {
            record["action"]["requester_id"],
            record["action"]["approver_id"],
        }:
            raise HTTPException(404, "Not found")
        return self.public(record)

    async def decide(
        self,
        tenant: str,
        task: str,
        run: str,
        approval_id: str,
        decision: BoundDecision,
    ) -> dict[str, Any]:
        raw, record = await self._read(tenant, task, run, approval_id)
        lease = self._current("agent:approve")
        if (
            lease.claims["sub"] != record["action"]["approver_id"]
            or lease.claims["sub"] == record["action"]["requester_id"]
        ):
            raise HTTPException(403, "Assigned separate approver required")
        self._valid(record, decision.action_hash)
        if record["status"] != "pending":
            raise HTTPException(409, "Approval already decided")
        await authorize_effect("agent:approve")
        now = int(time.time())
        record.update(
            status="approved" if decision.approved else "rejected",
            approver=binding(lease.claims),
            decided_at=now,
        )
        if decision.approved:
            nonce = secrets.token_bytes(12)
            aad = canonical([tenant, approval_id, record["action_hash"]]).encode()
            record["_credential"] = base64.b64encode(
                nonce + self.cipher.encrypt(nonce, lease.token.encode(), aad)
            ).decode()
        await self._commit(record, raw, now)
        return self.public(record)

    async def consume(
        self, tenant: str, task: str, run: str, approval_id: str, payload: BoundConsume
    ) -> dict[str, Any]:
        raw, record = await self._read(tenant, task, run, approval_id)
        requester = self._current("agent:execute")
        if binding(requester.claims) != record["requester"]:
            raise HTTPException(404, "Not found")
        self._valid(record, payload.action_hash)
        if record["status"] != "approved":
            raise HTTPException(409, "Approval is not consumable")
        try:
            ciphertext = base64.b64decode(record["_credential"], validate=True)
            aad = canonical([tenant, approval_id, record["action_hash"]]).encode()
            token = self.cipher.decrypt(ciphertext[:12], ciphertext[12:], aad).decode()
            claims = verify_access(token, get_settings())
            if (
                binding(claims) != record["approver"]
                or "agent:approve" not in claims["perms"]
            ):
                raise ValueError
            approver = AuthorityLease(token, claims, requester.client)
        except Exception:
            raise HTTPException(409, "Approval credential expired or changed") from None
        # Reuse the safe existing tool adapter. Calculation has no outside effect;
        # publication below is the protected effect, atomic with consumption.
        from app.agent.tools.builtins.mock_tools import CalculatorTool

        result = await CalculatorTool().execute(record["action"]["arguments"])
        if not result.success:
            raise HTTPException(422, "Invalid calculator action")
        await approver.check(force=True)
        await authorize_effect("agent:execute")
        now = int(time.time())
        record.update(status="consumed", consumed_at=now, result=result.output)
        record.pop("_credential", None)
        await self._commit(record, raw, now)
        return self.public(record)

    async def cancel(
        self,
        tenant: str,
        task: str,
        run: str,
        approval_id: str,
        *,
        permission: str = "agent:execute",
    ) -> dict[str, Any]:
        raw, record = await self._read(tenant, task, run, approval_id)
        lease = self._current(permission)
        if binding(lease.claims) != record["requester"]:
            raise HTTPException(404, "Not found")
        if record["status"] not in {"pending", "approved"}:
            raise HTTPException(409, "Approval already terminal")
        await authorize_effect(permission)
        record.update(status="cancelled")
        record.pop("_credential", None)
        await self._commit(record, raw, int(time.time()))
        return self.public(record)
