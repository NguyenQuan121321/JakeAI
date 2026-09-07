"""Unit tests for TwoZonePromptCompiler (Tier 5: Provider Prompt Caching).

Verifies:
1. Strict separation of Zone 1 (Static Prefix) and Zone 2 (Dynamic Suffix).
2. Deterministic serialization and SHA-256 fingerprinting.
3. Volatile request data isolation (UUIDs, timestamps, session IDs).
4. Cache versioning and prefix hash invalidation.
5. Message partitioning and token threshold eligibility.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.optimizer.two_zone_compiler import (
    ContaminationError,
    TwoZonePromptCompiler,
    get_two_zone_compiler,
)


def test_two_zone_compiler_separation() -> None:
    """Verifies that static instructions and dynamic queries are cleanly partitioned."""
    compiler = TwoZonePromptCompiler(min_cache_tokens=50)

    system_instruction = "You are a professional financial audit AI assistant."
    tools = [
        {
            "name": "lookup_transaction",
            "description": "Look up bank transaction by ID",
            "parameters": {
                "type": "object",
                "properties": {"tx_id": {"type": "string"}},
            },
        }
    ]
    static_context = "Company Policy: Follow GAAP regulations."
    user_query = "Audit invoice #48291 for tax discrepancies."
    dynamic_context = "Context: Invoice amount is $50,000 USD."

    compiled = compiler.compile(
        system_instruction=system_instruction,
        tools=tools,
        static_context=static_context,
        user_query=user_query,
        dynamic_context=dynamic_context,
        prompt_version="v1.0",
    )

    # Static Prefix should contain system prompt, tools, and static policy
    assert system_instruction in compiled.static_prefix
    assert "lookup_transaction" in compiled.static_prefix
    assert static_context in compiled.static_prefix

    # Dynamic Suffix should contain user query and dynamic invoice context
    assert user_query in compiled.dynamic_suffix
    assert dynamic_context in compiled.dynamic_suffix

    # Static Prefix MUST NOT contain dynamic user query
    assert user_query not in compiled.static_prefix
    assert dynamic_context not in compiled.static_prefix

    # Full prompt merges both
    full = compiled.full_prompt
    assert compiled.static_prefix in full
    assert compiled.dynamic_suffix in full
    assert (
        compiled.total_token_count
        == compiled.static_token_count + compiled.dynamic_token_count
    )


def test_static_prefix_determinism() -> None:
    """Verifies byte-identical SHA-256 hash regardless of tool declaration order or dict keys."""
    compiler = TwoZonePromptCompiler()

    tools_order_a = [
        {"name": "zebra_tool", "description": "Zebra", "z_key": 1, "a_key": 2},
        {"name": "alpha_tool", "description": "Alpha", "b_key": "bar", "a_key": "foo"},
    ]
    tools_order_b = [
        {"name": "alpha_tool", "a_key": "foo", "b_key": "bar", "description": "Alpha"},
        {"a_key": 2, "description": "Zebra", "name": "zebra_tool", "z_key": 1},
    ]

    compiled_a = compiler.compile(
        system_instruction="Static instructions\r\nwith Windows line endings",
        tools=tools_order_a,
        user_query="Query A",
    )

    compiled_b = compiler.compile(
        system_instruction="Static instructions\nwith Windows line endings",
        tools=tools_order_b,
        user_query="Query B with different user text",
    )

    # Prefix hashes MUST be identical despite dict key reordering, tool list reordering,
    # line ending differences (\r\n vs \n), and different user queries!
    assert compiled_a.static_prefix_hash == compiled_b.static_prefix_hash
    assert len(compiled_a.static_prefix_hash) == 64


def test_volatile_data_detection_and_isolation() -> None:
    """Verifies that volatile identifiers (UUIDs, timestamps) in Zone 1 are flagged or rejected."""
    compiler_strict = TwoZonePromptCompiler(strict_isolation=True)
    compiler_permissive = TwoZonePromptCompiler(strict_isolation=False)

    random_uuid = str(uuid.uuid4())
    iso_time = datetime.now(UTC).isoformat()

    dirty_system = f"System prompt with request_id: {random_uuid} at {iso_time}"

    # Permissive mode records violations in metadata
    compiled_permissive = compiler_permissive.compile(
        system_instruction=dirty_system,
        user_query="Normal user query",
    )
    assert compiled_permissive.metadata["contamination_detected"] is True
    reasons = compiled_permissive.metadata["contamination_reasons"]
    assert any("UUID" in r for r in reasons)
    assert any("timestamp" in r for r in reasons)

    # Strict mode raises ContaminationError
    with pytest.raises(ContaminationError, match="Zone 1 contamination detected"):
        compiler_strict.compile(
            system_instruction=dirty_system,
            user_query="Normal user query",
        )


def test_prefix_hash_invalidation_on_content_change() -> None:
    """Verifies that changes in static prompt, tool schema, or version cleanly update the hash."""
    compiler = TwoZonePromptCompiler()

    base = compiler.compile(
        system_instruction="Base System v1",
        tools=[{"name": "t1"}],
        prompt_version="v1.0",
    )

    # 1. System change
    diff_sys = compiler.compile(
        system_instruction="Base System v2",
        tools=[{"name": "t1"}],
        prompt_version="v1.0",
    )
    assert base.static_prefix_hash != diff_sys.static_prefix_hash

    # 2. Tool change
    diff_tool = compiler.compile(
        system_instruction="Base System v1",
        tools=[{"name": "t1"}, {"name": "t2"}],
        prompt_version="v1.0",
    )
    assert base.static_prefix_hash != diff_tool.static_prefix_hash

    # 3. Version bump (Cache invalidation)
    diff_version = compiler.compile(
        system_instruction="Base System v1",
        tools=[{"name": "t1"}],
        prompt_version="v2.0",
    )
    assert base.static_prefix_hash != diff_version.static_prefix_hash


def test_partition_messages() -> None:
    """Verifies partitioning of standard chat messages into static prefix and dynamic suffix."""
    compiler = get_two_zone_compiler()

    messages = [
        {"role": "system", "content": "You are a senior financial auditor."},
        {"role": "developer", "content": "Adhere strictly to SOX compliance rules."},
        {"role": "user", "content": "Check Q3 tax report for anomalies."},
        {
            "role": "assistant",
            "content": "Understood, please provide the balance sheet.",
        },
        {"role": "user", "content": "Here is the balance sheet: ..."},
    ]

    compiled = compiler.partition_messages(messages)

    assert "senior financial auditor" in compiled.static_prefix
    assert "SOX compliance rules" in compiled.static_prefix
    assert "Check Q3 tax report" in compiled.dynamic_suffix
    assert "Here is the balance sheet" in compiled.dynamic_suffix


def test_cache_eligibility_threshold() -> None:
    """Verifies cache eligibility threshold based on token count."""
    compiler = TwoZonePromptCompiler(min_cache_tokens=100)

    short_prompt = compiler.compile(
        system_instruction="Short system prompt.",
        user_query="Hello",
    )
    assert short_prompt.is_cache_eligible is False

    long_system = "Detailed enterprise financial regulations policy. " * 30
    long_prompt = compiler.compile(
        system_instruction=long_system,
        user_query="Hello",
    )
    assert long_prompt.is_cache_eligible is True


def test_tenant_isolation_prevents_cross_tenant_cache_leak() -> None:
    """Verifies that static prompts for different tenants produce isolated prefix hashes."""
    compiler = TwoZonePromptCompiler()

    static_rules = "Internal company rules and financial guidelines."

    env_tenant_a = compiler.compile(
        system_instruction=static_rules,
        user_query="Run audit",
        tenant_id="tenant-alpha",
    )
    env_tenant_b = compiler.compile(
        system_instruction=static_rules,
        user_query="Run audit",
        tenant_id="tenant-beta",
    )

    assert env_tenant_a.tenant_id == "tenant-alpha"
    assert env_tenant_b.tenant_id == "tenant-beta"
    # Strict tenant isolation: prefix hashes MUST NOT match across tenants
    assert env_tenant_a.static_prefix_hash != env_tenant_b.static_prefix_hash
