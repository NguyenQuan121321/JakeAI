"""Original J02 failures at the actual verifier, dependency and approval seams."""

import time
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException

from app.agent.approvals.manager import ApprovalManager
from app.agent.approvals.models import ApprovalDecision
from app.core.config import get_settings
from app.core.context import TenantContext
from app.core.security import check_token_denylist, verify_finnapigo_jwt


def legacy_token(**changes):
    now = int(time.time())
    claims = {
        "sub": "42",
        "uid": 42,
        "tid": "tenant-a",
        "type": "access",
        "iat": now,
        "exp": now + 600,
        "perms": [],
    }
    claims.update(changes)
    return jwt.encode(claims, get_settings().JWT_SECRET_KEY, algorithm="HS256")


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "attacker", "aud": ["other-service"]},
        {"tenant_id": "substituted"},
        {"uid": True},
        {"permissions": ["agent:execute"]},
    ],
)
def test_original_incomplete_or_ambiguous_identity_is_denied(changes):
    with pytest.raises(HTTPException) as error:
        verify_finnapigo_jwt(legacy_token(**changes))
    assert error.value.status_code == 401


def test_original_role_does_not_create_permissions():
    context = TenantContext(tenant_id="default", user_id="42", roles=["admin"])
    assert not context.has_permission("agent:execute")
    assert not context.has_all_permissions(["byok:write"])


@pytest.mark.asyncio
async def test_original_unknown_state_is_unavailable(monkeypatch):
    import redis.asyncio

    client = AsyncMock()
    client.exists.side_effect = ConnectionError("synthetic authority outage")
    monkeypatch.setattr(redis.asyncio, "from_url", lambda *a, **kw: client)
    with pytest.raises(HTTPException) as error:
        await check_token_denylist(legacy_token(jti="probe", sid="session"))
    assert error.value.status_code == 503


def test_original_approval_without_bound_authority_cannot_resume():
    manager = ApprovalManager()
    request = manager.create_request("task", "run", "tenant-a", "terminal", {}, "probe")
    with pytest.raises((PermissionError, ValueError, HTTPException)):
        manager.decide(
            request.approval_id, ApprovalDecision(approved=True), "tenant-a", "42"
        )
