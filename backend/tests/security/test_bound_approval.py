"""Actual ASGI/strict-token regressions with a component store double.

These tests do not establish Redis durability or worker safety. The hosted
actual Finn/Jake rehearsal separately exercises that real boundary.
"""

import asyncio
import base64
import json
import secrets
import time

import pytest

from app.agent.approvals import authority as module
from app.core.config import get_settings
from tests.fixtures.auth import create_test_jwt


@pytest.fixture
def component_authority(monkeypatch):
    records = {}
    lock = asyncio.Lock()

    class ComponentStore:
        epoch = 1

        def __init__(self, _url):
            self.client = self

        async def check(self, **kwargs):
            pass

        async def aclose(self):
            pass

        async def get(self, key):
            if key == module.POLICY_KEY:
                return module.canonical(
                    {
                        "epoch": self.epoch,
                        "policy": "approval-calculator-v1",
                        "tool": "calculator-v1",
                    }
                )
            return records.get(key)

        async def eval(
            self, script, count, key, policy_key, prior, value, expires, checked, policy
        ):
            async with lock:
                if policy != module.canonical(
                    {
                        "epoch": self.epoch,
                        "policy": "approval-calculator-v1",
                        "tool": "calculator-v1",
                    }
                ):
                    return -4
                now = int(time.time())
                if now >= int(expires):
                    return -1
                if now - int(checked) > 2:
                    return -2
                if (records.get(key) or "") != prior:
                    return 0
                records[key] = value
                return 1

    monkeypatch.setattr(module, "RedisStore", ComponentStore)
    monkeypatch.setenv("APPROVAL_REDIS_URL", "redis://:synthetic@approval-test:6379/0")
    monkeypatch.setenv(
        "APPROVAL_CREDENTIAL_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    get_settings.cache_clear()
    yield records
    get_settings.cache_clear()


def headers(sub="11", tenant="approval-a", permissions=None, **claims):
    return {
        "Authorization": "Bearer "
        + create_test_jwt(
            sub=sub,
            tenant_id=tenant,
            permissions=permissions
            if permissions is not None
            else ["agent:read", "agent:write", "agent:execute", "agent:approve"],
            **claims,
        )
    }


async def proposed(client, expires=300, approver="22", expression="6 * 7"):
    task = await client.post(
        "/api/v1/agent/tasks",
        headers=headers(),
        json={"goal": "Publish an approved calculation"},
    )
    assert task.status_code == 201, task.text
    prefix = "/api/v1/agent/tasks/" + task.json()["task_id"] + "/runs"
    run = await client.post(
        prefix,
        headers=headers(),
        json={
            "approval": {
                "approver_id": approver,
                "expression": expression,
                "expires_in": expires,
            }
        },
    )
    assert run.status_code == 201, run.text
    data = run.json()
    path = prefix + "/" + data["run_id"] + "/approvals/" + data["pending_approval_id"]
    record = await client.get(path, headers=headers())
    assert record.status_code == 200, record.text
    return path, record.json()


async def approved(client):
    path, record = await proposed(client)
    decision = await client.post(
        path,
        headers=headers("22"),
        json={"approved": True, "action_hash": record["action_hash"]},
    )
    assert decision.status_code == 200, decision.text
    return path, record


@pytest.mark.asyncio
async def test_authorized_publication_and_one_time_consume(
    async_client, component_authority
):
    path, record = await approved(async_client)
    # Worker-local task/run data cannot grant authority or be required by a peer.
    from app.agent.runtime.manager import get_agent_manager

    get_agent_manager()._tasks.clear()
    result = await async_client.post(
        path + "/consume",
        headers=headers(),
        json={"action_hash": record["action_hash"]},
    )
    assert result.status_code == 200, result.text
    assert result.json()["result"] == {"expression": "6 * 7", "result": 42}
    assert result.json()["status"] == "consumed"
    assert "_credential" not in result.text
    replay = await async_client.post(
        path + "/consume",
        headers=headers(),
        json={"action_hash": record["action_hash"]},
    )
    assert replay.status_code == 409
    assert all(
        "_credential" not in json.loads(value) for value in component_authority.values()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,caller,expected",
    [
        ("decision", headers("11"), 403),
        ("decision", headers("33"), 403),
        ("decision", headers("22", "approval-b"), 404),
        ("decision", headers("22", permissions=["agent:read"]), 403),
        ("consume", headers("33"), 404),
        ("consume", headers("11", "approval-b"), 404),
        ("consume", headers("11", permissions=["agent:read"]), 403),
        ("consume", headers("11", sid="another-session"), 404),
        ("read", headers("33"), 404),
        ("cancel", headers("33"), 404),
    ],
)
async def test_binding_denials(
    async_client, component_authority, operation, caller, expected
):
    path, record = await proposed(async_client)
    if operation == "read":
        response = await async_client.get(path, headers=caller)
    else:
        body = {"action_hash": record["action_hash"]}
        if operation == "decision":
            body["approved"] = True
        response = await async_client.post(
            path + ("" if operation == "decision" else "/" + operation),
            headers=caller,
            json=body,
        )
    assert response.status_code == expected, response.text
    assert (
        json.loads(next(reversed(component_authority.values())))["status"] == "pending"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal",
    [
        "reject",
        "cancel",
        "pending",
        "hash",
        "policy",
        "tool",
        "expiry",
        "ciphertext",
        "approver-state",
        "requester-state",
    ],
)
async def test_consume_failures_preserve_unpublished_result(
    async_client, component_authority, monkeypatch, terminal
):
    path, record = await proposed(async_client)
    body = {"action_hash": record["action_hash"]}
    if terminal != "pending":
        res = await async_client.post(
            path, headers=headers("22"), json={**body, "approved": terminal != "reject"}
        )
        assert res.status_code == 200
    if terminal == "cancel":
        assert (
            await async_client.post(path + "/cancel", headers=headers())
        ).status_code == 200
    if terminal == "hash":
        body["action_hash"] = "0" * 64
    if terminal in {"policy", "tool"}:
        monkeypatch.setattr(
            module,
            "POLICY_VERSION" if terminal == "policy" else "TOOL_VERSION",
            "changed",
        )
    if terminal == "expiry":
        raw = json.loads(next(reversed(component_authority.values())))
        monkeypatch.setattr(
            module.time, "time", lambda: raw["action"]["expires_at"] + 1
        )
    if terminal == "ciphertext":
        key = next(reversed(component_authority))
        raw = json.loads(component_authority[key])
        raw["_credential"] = "broken"
        component_authority[key] = json.dumps(raw)
    if terminal.endswith("-state"):
        from fastapi import HTTPException

        from app.main import app

        class Fault:
            settings = get_settings()

            async def check(self, token, claims):
                if claims["sub"] == ("22" if terminal == "approver-state" else "11"):
                    raise HTTPException(503, "Identity authority unavailable")

        monkeypatch.setattr(app.state, "identity_client", Fault(), raising=False)
    result = await async_client.post(path + "/consume", headers=headers(), json=body)
    assert result.status_code in (
        {503} if terminal.endswith("-state") else {401, 409}
    ), result.text
    assert json.loads(next(reversed(component_authority.values())))["result"] is None


@pytest.mark.asyncio
async def test_concurrent_component_transitions(async_client, component_authority):
    path, record = await approved(async_client)
    results = await asyncio.gather(
        *(
            async_client.post(
                path + "/consume",
                headers=headers(),
                json={"action_hash": record["action_hash"]},
            )
            for _ in range(12)
        )
    )
    assert [r.status_code for r in results].count(200) == 1
    assert [r.status_code for r in results].count(409) == 11


@pytest.mark.asyncio
async def test_run_cancellation_invalidates_bound_authority(
    async_client, component_authority
):
    path, record = await approved(async_client)
    run_path = path.split("/approvals/")[0]
    cancelled = await async_client.post(run_path + "/cancel", headers=headers())
    assert cancelled.status_code == 200, cancelled.text
    assert (
        await async_client.post(
            path + "/consume",
            headers=headers(),
            json={"action_hash": record["action_hash"]},
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_unsafe_action_cannot_enter_positive_seam(
    async_client, component_authority
):
    task = await async_client.post(
        "/api/v1/agent/tasks",
        headers=headers(),
        json={"goal": "Unsafe input must be denied"},
    )
    response = await async_client.post(
        "/api/v1/agent/tasks/" + task.json()["task_id"] + "/runs",
        headers=headers(),
        json={
            "approval": {
                "approver_id": "22",
                "expression": "6 * 7",
                "tool_name": "terminal_exec",
            }
        },
    )
    assert response.status_code == 422
    assert component_authority == {}


@pytest.mark.asyncio
async def test_shared_policy_generation_invalidates_old_and_allows_new(
    async_client, component_authority, monkeypatch
):
    path, record = await approved(async_client)
    monkeypatch.setattr(module.RedisStore, "epoch", 2)
    assert (
        await async_client.post(
            path + "/consume",
            headers=headers(),
            json={"action_hash": record["action_hash"]},
        )
    ).status_code == 409
    new_path, new_record = await approved(async_client)
    assert new_record["action"]["policy_epoch"] == 2
    assert (
        await async_client.post(
            new_path + "/consume",
            headers=headers(),
            json={"action_hash": new_record["action_hash"]},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_lost_commit_reply_does_not_restore_one_time_authority(
    async_client, component_authority, monkeypatch
):
    path, record = await approved(async_client)
    original = module.RedisStore.eval

    async def lost_reply(self, *args):
        await original(self, *args)
        raise TimeoutError("synthetic lost acknowledgement")

    monkeypatch.setattr(module.RedisStore, "eval", lost_reply)
    result = await async_client.post(
        path + "/consume",
        headers=headers(),
        json={"action_hash": record["action_hash"]},
    )
    assert result.status_code == 503
    observed = await async_client.get(path, headers=headers())
    assert observed.json()["status"] == "consumed"
    assert observed.json()["result"]["result"] == 42
    assert (
        await async_client.post(
            path + "/consume",
            headers=headers(),
            json={"action_hash": record["action_hash"]},
        )
    ).status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("APPROVAL_REDIS_URL", ""),
        ("APPROVAL_REDIS_URL", "redis://localhost:6379/0"),
        ("APPROVAL_CREDENTIAL_KEY", "bad"),
        ("APPROVAL_CREDENTIAL_KEY", "same-signing-key"),
    ],
)
def test_invalid_configuration_fails_closed(
    component_authority, monkeypatch, field, value
):
    from fastapi import HTTPException

    if value == "same-signing-key":
        value = get_settings().JWT_SECRET_KEY
    monkeypatch.setenv(field, value)
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as error:
        module.ApprovalAuthority()
    assert error.value.status_code == 503
