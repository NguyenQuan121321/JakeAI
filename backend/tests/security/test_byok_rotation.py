"""Same rotation/fault protocol against memory and opt-in real isolated Redis."""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import uuid

import pytest

from app.core.byok import BYOKManager
from app.core.byok_storage import BYOKError, MemoryStore, RedisStore


def material():
    return base64.b64encode(secrets.token_bytes(32)).decode()


@pytest.fixture(params=["memory", "redis"])
async def store(request):
    if request.param == "memory":
        yield MemoryStore()
        return
    url = os.getenv("J03_REDIS_URL")
    if not url:
        pytest.skip("BLOCKED: J03_REDIS_URL must name an isolated synthetic Redis")
    value = RedisStore(url)
    await value.check()
    before = set(await value.client.keys("byok:*"))
    try:
        yield value
    finally:
        after = set(await value.client.keys("byok:*"))
        for key in after - before:
            await value.client.delete(key)
        await value.client.aclose()


@pytest.fixture
def tenant():
    return "j03-" + uuid.uuid4().hex


def ring(store, old, current):
    return BYOKManager(
        current, key_id="current", previous_keys={"old": old}, store=store
    )


async def full_pass(manager):
    reports, cursor = [], "0"
    while True:
        report = await manager.reencrypt_batch(cursor, count=2)
        reports.append(report)
        cursor = report["cursor"]
        if cursor == "0":
            return reports


async def test_partial_migration_retry_restart_and_restore(store, tenant, monkeypatch):
    old, current = material(), material()
    legacy = BYOKManager(old, key_id="old", store=store)
    canary = secrets.token_urlsafe(24)
    for provider in ["openai", "groq", "anthropic"]:
        await legacy.store_key(tenant, provider, canary, actor_id="owner")
    migrator = ring(store, old, current)
    original_cas = store.cas
    calls = 0

    async def partial(key, expected, value):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise BYOKError("BYOK_STORAGE_UNAVAILABLE")
        return await original_cas(key, expected, value)

    monkeypatch.setattr(store, "cas", partial)
    reports = await full_pass(migrator)
    assert sum(r["migrated"] for r in reports) == 2
    assert sum(r["errors"].get("BYOK_STORAGE_UNAVAILABLE", 0) for r in reports) == 1
    monkeypatch.setattr(store, "cas", original_cas)
    # New manager/connection reconstructs persisted state without local key/ciphertext fallback.
    restarted_store = (
        RedisStore(os.environ["J03_REDIS_URL"])
        if isinstance(store, RedisStore)
        else store
    )
    try:
        restarted = ring(restarted_store, old, current)
        assert sum(r["migrated"] for r in await full_pass(restarted)) == 1
        assert all(
            not r["errors"] and not r["migrated"] for r in await full_pass(restarted)
        )
        without_old = BYOKManager(
            current, key_id="current", store=restarted_store, retired_key_ids=["old"]
        )
        for provider in ["openai", "groq", "anthropic"]:
            assert await without_old.get_decrypted_key(tenant, provider) == canary
        snapshot = await restarted._get_raw_val(tenant, "openai")
        restored = BYOKManager(current, key_id="current", store=MemoryStore())
        await restored._save_raw_val(tenant, "openai", snapshot)
        assert await restored.get_decrypted_key(tenant, "openai") == canary
        wrong_restore = BYOKManager(material(), key_id="current", store=restored.store)
        with pytest.raises(BYOKError, match="BYOK_RECORD_CORRUPT"):
            await wrong_restore.get_decrypted_key(tenant, "openai")
    finally:
        if restarted_store is not store:
            await restarted_store.client.aclose()


async def test_concurrent_migrators_readers_and_current_writer(
    store, tenant, monkeypatch
):
    old, current = material(), material()
    original, replacement = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    await BYOKManager(old, key_id="old", store=store).store_key(
        tenant, "openai", original
    )
    manager = ring(store, old, current)
    original_cas = store.cas
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(key, expected, value):
        if expected and json.loads(expected)["kid"] == "old" and not entered.is_set():
            entered.set()
            await release.wait()
        return await original_cas(key, expected, value)

    monkeypatch.setattr(store, "cas", delayed)
    first = asyncio.create_task(full_pass(manager))
    await asyncio.wait_for(entered.wait(), 3)
    reads = await asyncio.gather(
        *(manager.get_decrypted_key(tenant, "openai") for _ in range(20))
    )
    assert all(value == original for value in reads)
    await manager.rotate_key(tenant, "openai", replacement)
    second = await full_pass(ring(store, old, current))
    release.set()
    first_reports = await first
    assert sum(r["conflicts"] for r in first_reports) == 1
    assert all(not r["migrated"] for r in second)
    assert await manager.get_decrypted_key(tenant, "openai") == replacement
    assert json.loads(await manager._get_raw_val(tenant, "openai"))["kid"] == "current"


@pytest.mark.parametrize("operation", ["rotate", "validate", "revoke", "delete"])
async def test_stale_mutation_cannot_overwrite_current_write(
    store, tenant, monkeypatch, operation
):
    manager = BYOKManager(store=store)
    await manager.store_key(tenant, "openai", secrets.token_urlsafe(24))
    prior_cas = store.cas
    competing = secrets.token_urlsafe(24)
    interfered = False

    async def race(key, expected, value):
        nonlocal interfered
        if not interfered:
            interfered = True
            await manager.store_key(tenant, "openai", competing)
        return await prior_cas(key, expected, value)

    async def accepted(*args):
        return True, None

    monkeypatch.setattr(store, "cas", race)
    monkeypatch.setattr(manager, "validate_key", accepted)
    with pytest.raises(BYOKError, match="BYOK_CONFLICT"):
        if operation == "rotate":
            await manager.rotate_key(tenant, "openai", secrets.token_urlsafe(24))
        elif operation == "validate":
            await manager.validate_stored_key(tenant, "openai")
        elif operation == "revoke":
            await manager.revoke_key(tenant, "openai")
        else:
            await manager.delete_key(tenant, "openai")
    assert await manager.get_decrypted_key(tenant, "openai") == competing


async def test_retirement_unknown_corruption_legacy_and_key_provider_failure(
    store, tenant, monkeypatch
):
    old, current = material(), material()
    await BYOKManager(old, key_id="old", store=store).store_key(
        tenant, "openai", secrets.token_urlsafe(24)
    )
    missing = BYOKManager(current, key_id="current", store=store)
    with pytest.raises(BYOKError, match="BYOK_KEY_UNKNOWN"):
        await missing.get_decrypted_key(tenant, "openai")
    retired = BYOKManager(
        current, key_id="current", retired_key_ids=["old"], store=store
    )
    with pytest.raises(BYOKError, match="BYOK_KEY_RETIRED"):
        await retired.get_decrypted_key(tenant, "openai")
    for kwargs in [
        {"key_id": "old", "retired_key_ids": ["old"]},
        {
            "key_id": "renamed",
            "retired_key_hashes": [hashlib.sha256(base64.b64decode(old)).hexdigest()],
        },
        {
            "key_id": "current",
            "previous_keys": {"old": old},
            "retired_key_ids": ["old"],
        },
    ]:
        with pytest.raises(BYOKError, match="BYOK_KEY_UNAVAILABLE"):
            BYOKManager(old, store=store, **kwargs)
    with pytest.raises(BYOKError, match="BYOK_KEY_UNAVAILABLE"):
        BYOKManager("", store=store)
    await missing._save_raw_val(tenant, "groq", "corrupt")
    with pytest.raises(BYOKError, match="BYOK_RECORD_CORRUPT"):
        await missing.get_decrypted_key(tenant, "groq")
    report = await full_pass(missing)
    assert sum(sum(r["errors"].values()) for r in report) >= 2
    legacy_name = f"byok:{tenant}:deepseek"
    await store.cas(legacy_name, None, "unversioned")
    with pytest.raises(BYOKError, match="BYOK_LEGACY_RECORD"):
        await missing.get_decrypted_key(tenant, "deepseek")


async def test_outage_never_succeeds_or_uses_process_fallback(
    store, tenant, monkeypatch
):
    manager = BYOKManager(store=store)
    await manager.store_key(tenant, "openai", secrets.token_urlsafe(24))

    async def unavailable(*args):
        raise BYOKError("BYOK_STORAGE_UNAVAILABLE")

    with monkeypatch.context() as fault:
        fault.setattr(store, "get", unavailable)
        for operation in [
            manager.get_decrypted_key,
            manager.delete_key,
            manager.revoke_key,
        ]:
            with pytest.raises(BYOKError, match="BYOK_STORAGE_UNAVAILABLE"):
                await operation(tenant, "openai")
        with pytest.raises(BYOKError, match="BYOK_STORAGE_UNAVAILABLE"):
            await manager.store_key(tenant, "groq", secrets.token_urlsafe(24))
    with monkeypatch.context() as fault:
        fault.setattr(store, "cas", unavailable)
        with pytest.raises(BYOKError, match="BYOK_STORAGE_UNAVAILABLE"):
            await manager.delete_key(tenant, "openai")
    assert await manager.get_decrypted_key(tenant, "openai")


async def test_real_redis_connection_fault_is_truthful(tenant):
    store = RedisStore("redis://127.0.0.1:1/0")
    try:
        manager = BYOKManager(store=store)
        with pytest.raises(BYOKError, match="BYOK_STORAGE_UNAVAILABLE"):
            await manager.store_key(tenant, "openai", secrets.token_urlsafe(24))
        with pytest.raises(BYOKError, match="BYOK_STORAGE_UNAVAILABLE"):
            await store.check()
        with pytest.raises(BYOKError, match="BYOK_STORAGE_UNAVAILABLE"):
            await store.scan("0", 100)
        with pytest.raises(BYOKError, match="BYOK_STORAGE_UNAVAILABLE"):
            await store.cas("synthetic", None, "encrypted")
    finally:
        await store.client.aclose()


async def test_two_concurrent_migrators_only_commit_once(store, tenant, monkeypatch):
    old, current = material(), material()
    await BYOKManager(old, key_id="old", store=store).store_key(
        tenant, "openai", secrets.token_urlsafe(24)
    )
    first_manager, second_manager = ring(store, old, current), ring(store, old, current)
    original_cas = store.cas
    entered, release = asyncio.Event(), asyncio.Event()

    async def interleave(key, expected, value):
        if not entered.is_set():
            entered.set()
            await release.wait()
        return await original_cas(key, expected, value)

    monkeypatch.setattr(store, "cas", interleave)
    first = asyncio.create_task(full_pass(first_manager))
    await asyncio.wait_for(entered.wait(), 3)
    second = await full_pass(second_manager)
    release.set()
    first_reports = await first
    assert sum(r["migrated"] for r in second) == 1
    assert sum(r["conflicts"] for r in first_reports) == 1
    assert (
        json.loads(await first_manager._get_raw_val(tenant, "openai"))["revision"] == 2
    )
