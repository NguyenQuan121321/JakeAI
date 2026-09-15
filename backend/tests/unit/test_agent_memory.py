"""Unit tests for agent memory architectures, tenant isolation, and search filtering (UNIT-054).

Covers:
1. LongTermMemory: tenant isolation, user scoping, TTL expiration, search matching.
2. ShortTermMemory: FIFO eviction with system prompt retention, snapshot/restore, key lookup.
3. AgentMemoryManager: coordination, per-run buffers, episodic memory persistence and recall.
"""

from __future__ import annotations

import time

from app.agent.backends.base import AgentMessage
from app.agent.memory.base import MemoryScope
from app.agent.memory.long_term import LongTermMemory
from app.agent.memory.manager import AgentMemoryManager
from app.agent.memory.short_term import ShortTermMemory

# ==============================================================================
# 1. LongTermMemory Tests
# ==============================================================================


def test_long_term_memory_store_and_get() -> None:
    """Entry stored in LongTermMemory can be retrieved by id within same tenant."""
    ltm = LongTermMemory()
    entry = ltm.store(
        tenant_id="tenant_alpha",
        key="customer_preference",
        value={"theme": "dark", "currency": "USD"},
        summary="User preferred UI theme and default currency",
    )

    assert entry.entry_id.startswith("ltm_")
    assert entry.tenant_id == "tenant_alpha"
    assert entry.scope == MemoryScope.LONG_TERM
    assert entry.value == {"theme": "dark", "currency": "USD"}

    retrieved = ltm.get("tenant_alpha", entry.entry_id)
    assert retrieved is not None
    assert retrieved.entry_id == entry.entry_id
    assert retrieved.key == "customer_preference"


def test_long_term_memory_strict_tenant_isolation() -> None:
    """Tenant A cannot retrieve or search memory stored by Tenant B."""
    ltm = LongTermMemory()
    entry = ltm.store(
        tenant_id="tenant_alpha",
        key="confidential_contract",
        value="Secret terms for Alpha",
    )

    # Cross-tenant get returns None
    assert ltm.get("tenant_beta", entry.entry_id) is None

    # Cross-tenant search returns empty
    results = ltm.search(tenant_id="tenant_beta", key_prefix="confidential")
    assert len(results) == 0

    # Origin tenant can find it
    alpha_results = ltm.search(tenant_id="tenant_alpha", key_prefix="confidential")
    assert len(alpha_results) == 1
    assert alpha_results[0].entry_id == entry.entry_id


def test_long_term_memory_ttl_expiration() -> None:
    """Entries past their TTL are lazily purged and not returned by get or search."""
    ltm = LongTermMemory()
    # Store entry with 1 second TTL
    entry = ltm.store(
        tenant_id="tenant_alpha",
        key="ephemeral_session_token",
        value="xyz123",
        ttl_seconds=1.0,
    )

    # Manually backdate created_at and expires_at to simulate expiration
    entry.created_at = time.time() - 10.0
    entry.expires_at = time.time() - 5.0

    # get() must return None and clean up entry
    assert ltm.get("tenant_alpha", entry.entry_id) is None

    # search() must exclude expired entry
    results = ltm.search(tenant_id="tenant_alpha", key_prefix="ephemeral")
    assert len(results) == 0


def test_long_term_memory_zero_ttl_is_permanent() -> None:
    """Entries stored with ttl_seconds <= 0 have expires_at == None and never expire."""
    ltm = LongTermMemory()
    entry = ltm.store(
        tenant_id="tenant_alpha",
        key="permanent_rule",
        value="Never expire",
        ttl_seconds=0.0,
    )
    assert entry.expires_at is None
    assert ltm.get("tenant_alpha", entry.entry_id) is not None


def test_long_term_memory_search_matching_rules() -> None:
    """Search matches via prefix, case-insensitive substring, word tokens, and summary."""
    ltm = LongTermMemory()
    # Match 1: prefix
    e1 = ltm.store(
        "tenant_alpha",
        key="user_account_settings",
        value=1,
        summary="account settings",
    )
    # Match 2: underscore word token match (e.g. 'settings')
    e2 = ltm.store(
        "tenant_alpha",
        key="system_settings_override",
        value=2,
        summary="override",
    )
    # Match 3: summary match
    e3 = ltm.store(
        "tenant_alpha",
        key="misc_blob",
        value=3,
        summary="Contains financial statement details",
    )
    # Non-match
    ltm.store("tenant_alpha", key="weather_forecast", value=4, summary="sunny")

    # Search for "settings"
    res_settings = ltm.search("tenant_alpha", key_prefix="settings")
    found_ids = {e.entry_id for e in res_settings}
    assert e1.entry_id in found_ids
    assert e2.entry_id in found_ids

    # Search for summary keyword "financial"
    res_financial = ltm.search("tenant_alpha", key_prefix="financial")
    assert len(res_financial) == 1
    assert res_financial[0].entry_id == e3.entry_id


def test_long_term_memory_user_id_filtering_and_limit() -> None:
    """Search respects user_id filter, limits result count, and orders newest first."""
    ltm = LongTermMemory()
    base_time = time.time()

    # Store entries for user_1 and user_2 with staggered timestamps
    entries = []
    for i in range(5):
        e = ltm.store(
            tenant_id="tenant_alpha",
            key=f"item_{i}",
            value=i,
            user_id="user_1",
        )
        e.created_at = base_time + i
        entries.append(e)

    # Another user's entry
    ltm.store(
        tenant_id="tenant_alpha",
        key="item_other",
        value=99,
        user_id="user_2",
    )

    # Search filtering by user_1 with limit 3
    results = ltm.search("tenant_alpha", user_id="user_1", limit=3)
    assert len(results) == 3
    # Returns in insertion order up to limit
    assert results[0].key == "item_0"
    assert results[1].key == "item_1"
    assert results[2].key == "item_2"


def test_long_term_memory_delete_and_clear_tenant() -> None:
    """delete removes single entry; clear_tenant purges all tenant entries."""
    ltm = LongTermMemory()
    e1 = ltm.store("tenant_alpha", "key1", "val1")
    e2 = ltm.store("tenant_alpha", "key2", "val2")
    e3 = ltm.store("tenant_beta", "key3", "val3")

    # Delete e1
    assert ltm.delete("tenant_alpha", e1.entry_id) is True
    assert ltm.delete("tenant_alpha", e1.entry_id) is False  # already deleted
    assert ltm.get("tenant_alpha", e1.entry_id) is None
    assert ltm.get("tenant_alpha", e2.entry_id) is not None

    # Clear tenant_alpha
    ltm.clear_tenant("tenant_alpha")
    assert ltm.get("tenant_alpha", e2.entry_id) is None

    # tenant_beta unaffected
    assert ltm.get("tenant_beta", e3.entry_id) is not None


# ==============================================================================
# 2. ShortTermMemory Tests
# ==============================================================================


def test_short_term_memory_store_and_lookup() -> None:
    """ShortTermMemory stores and looks up most recent value for key."""
    stm = ShortTermMemory(max_entries=5)
    stm.store(key="var_a", value=100)
    stm.store(key="var_a", value=200)  # updated value

    assert stm.get("var_a") == 200
    assert stm.get("nonexistent") is None
    assert len(stm.list_entries()) == 2


def test_short_term_memory_variable_fifo_eviction() -> None:
    """When entries exceed max_entries, oldest variable entry is evicted."""
    stm = ShortTermMemory(max_entries=3)
    stm.store(key="first", value=1)
    stm.store(key="second", value=2)
    stm.store(key="third", value=3)
    stm.store(key="fourth", value=4)  # triggers eviction of "first"

    assert len(stm.list_entries()) == 3
    assert stm.get("first") is None
    assert stm.get("second") == 2
    assert stm.get("fourth") == 4


def test_short_term_memory_message_eviction_preserves_system_prompt() -> None:
    """FIFO message eviction preserves system message at index 0 when capacity exceeded."""
    stm = ShortTermMemory(max_entries=3)

    msg_sys = AgentMessage(role="system", content="You are JakeAI.")
    msg_u1 = AgentMessage(role="user", content="Step 1")
    msg_a1 = AgentMessage(role="assistant", content="Response 1")
    msg_u2 = AgentMessage(role="user", content="Step 2")  # triggers eviction

    stm.add_message(msg_sys)
    stm.add_message(msg_u1)
    stm.add_message(msg_a1)
    assert len(stm.get_messages()) == 3

    stm.add_message(msg_u2)
    messages = stm.get_messages()
    assert len(messages) == 3

    # System message must still be at index 0
    assert messages[0].role == "system"
    assert messages[0].content == "You are JakeAI."
    # msg_u1 ("Step 1") was evicted, so index 1 is msg_a1
    assert messages[1].content == "Response 1"
    assert messages[2].content == "Step 2"


def test_short_term_memory_message_eviction_without_system_prompt() -> None:
    """FIFO message eviction without system prompt evicts index 0."""
    stm = ShortTermMemory(max_entries=2)
    msg1 = AgentMessage(role="user", content="User 1")
    msg2 = AgentMessage(role="assistant", content="Assistant 1")
    msg3 = AgentMessage(role="user", content="User 2")

    stm.add_message(msg1)
    stm.add_message(msg2)
    stm.add_message(msg3)

    messages = stm.get_messages()
    assert len(messages) == 2
    assert messages[0].content == "Assistant 1"
    assert messages[1].content == "User 2"


def test_short_term_memory_snapshot_and_restore() -> None:
    """Snapshot exports valid dict list and restore reconstructs exact state."""
    stm = ShortTermMemory(max_entries=10)
    stm.store(key="alpha", value={"status": "active"})
    stm.store(key="beta", value=[1, 2, 3])

    snap = stm.snapshot()
    assert len(snap) == 2
    assert isinstance(snap, list)
    assert snap[0]["key"] == "alpha"

    # New instance restoring snapshot
    stm2 = ShortTermMemory(max_entries=10)
    stm2.restore(snap)
    assert stm2.get("alpha") == {"status": "active"}
    assert stm2.get("beta") == [1, 2, 3]


def test_short_term_memory_clear() -> None:
    """Clear resets both entries and messages buffers."""
    stm = ShortTermMemory()
    stm.store(key="foo", value="bar")
    stm.add_message(AgentMessage(role="user", content="hello"))

    stm.clear()
    assert len(stm.list_entries()) == 0
    assert len(stm.get_messages()) == 0


# ==============================================================================
# 3. AgentMemoryManager Tests
# ==============================================================================


def test_agent_memory_manager_run_isolation() -> None:
    """AgentMemoryManager provides isolated short-term memory buffers per run_id."""
    mgr = AgentMemoryManager()

    mem_run1 = mgr.get_run_memory("run_1")
    mem_run2 = mgr.get_run_memory("run_2")

    mem_run1.store(key="status", value="run1_val")
    mem_run2.store(key="status", value="run2_val")

    assert mem_run1.get("status") == "run1_val"
    assert mem_run2.get("status") == "run2_val"

    mgr.remove_run_memory("run_1")
    # Fetching run_1 again creates a fresh buffer
    fresh_run1 = mgr.get_run_memory("run_1")
    assert fresh_run1.get("status") is None


def test_agent_memory_manager_episodic_workflow() -> None:
    """remember_episodic and recall_relevant coordinate through LongTermMemory."""
    mgr = AgentMemoryManager()
    mgr.remember_episodic(
        tenant_id="tenant_delta",
        key="project_status",
        value="Sprint 4 in progress",
        summary="Sprint status report",
    )

    recalled = mgr.recall_relevant(tenant_id="tenant_delta", query_key="project_status")
    assert len(recalled) == 1
    assert recalled[0].key == "project_status"
    assert recalled[0].value == "Sprint 4 in progress"

    # Different tenant recall returns empty
    cross_tenant = mgr.recall_relevant(
        tenant_id="tenant_other", query_key="project_status"
    )
    assert len(cross_tenant) == 0
