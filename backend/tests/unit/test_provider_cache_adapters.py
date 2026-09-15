"""Unit tests for Provider Prompt Cache adapters, policies, and usage extraction (UNIT-059).

Covers:
1. get_provider_cache_policy: resolution across Anthropic, OpenAI, DeepSeek, Gemini, Groq, and fallback.
2. evaluate_cache_eligibility: unsupported providers, minimum tokens, dynamic contamination, prefix hash changes.
3. AnthropicPromptCacheAdapter: explicit breakpoint insertion, usage extraction (cache_read & cache_creation).
4. OpenAIPromptCacheAdapter: payload structure, prompt_tokens_details cached token extraction.
5. GeminiPromptCacheAdapter: systemInstruction structure, usageMetadata extraction.
6. DeepSeekPromptCacheAdapter & GroqPromptCacheAdapter: usage extraction and unsupported reporting.
"""

from __future__ import annotations

import pytest

from app.optimizer.provider_cache_policy import (
    AnthropicPromptCacheAdapter,
    CacheMissReason,
    DeepSeekPromptCacheAdapter,
    GeminiPromptCacheAdapter,
    GroqPromptCacheAdapter,
    OpenAIPromptCacheAdapter,
    ProviderCacheStatus,
    evaluate_cache_eligibility,
    get_provider_adapter,
    get_provider_cache_policy,
)

# ==============================================================================
# 1. Policy Resolution & Eligibility Evaluation
# ==============================================================================


@pytest.mark.parametrize(
    ("identifier", "expected_status", "expected_min_tokens", "expected_breakpoint"),
    [
        ("claude-3-5-sonnet", ProviderCacheStatus.SUPPORTED, 1024, True),
        ("anthropic.claude-3-opus", ProviderCacheStatus.SUPPORTED, 1024, True),
        ("gpt-4o", ProviderCacheStatus.SUPPORTED, 1024, False),
        ("o1-mini", ProviderCacheStatus.SUPPORTED, 1024, False),
        ("deepseek-chat", ProviderCacheStatus.SUPPORTED, 64, False),
        ("gemini-1.5-pro", ProviderCacheStatus.PARTIALLY_SUPPORTED, 32768, True),
        ("groq", ProviderCacheStatus.NOT_SUPPORTED, 0, False),
    ],
)
def test_get_provider_cache_policy_resolution(
    identifier: str,
    expected_status: ProviderCacheStatus,
    expected_min_tokens: int,
    expected_breakpoint: bool,
) -> None:
    """Policies are correctly resolved with minimum tokens and breakpoint rules."""
    policy = get_provider_cache_policy(identifier)
    assert policy.status == expected_status
    assert policy.minimum_tokens == expected_min_tokens
    assert policy.explicit_breakpoint == expected_breakpoint


def test_get_provider_cache_policy_unknown_fallback() -> None:
    """Unknown provider or model identifiers return safe fallback policy."""
    policy = get_provider_cache_policy("unknown-experimental-model")
    assert policy.status == ProviderCacheStatus.UNKNOWN
    assert policy.enabled is False
    assert policy.mechanism == "none"


@pytest.mark.parametrize(
    (
        "policy_name",
        "tokens",
        "prev_hash",
        "curr_hash",
        "contaminated",
        "expected_eligible",
        "expected_reason",
    ),
    [
        # Unsupported provider
        (
            "groq",
            2000,
            None,
            None,
            False,
            False,
            CacheMissReason.PROVIDER_UNSUPPORTED,
        ),
        # Contaminated with dynamic data
        (
            "anthropic",
            2000,
            None,
            None,
            True,
            False,
            CacheMissReason.DYNAMIC_DATA_CONTAMINATION,
        ),
        # Below token threshold for Anthropic (min 1024)
        (
            "anthropic",
            500,
            None,
            None,
            False,
            False,
            CacheMissReason.BELOW_MINIMUM_SIZE,
        ),
        # Above threshold for DeepSeek (min 64)
        ("deepseek", 100, None, None, False, True, CacheMissReason.NONE),
        # Prefix changed
        (
            "openai",
            2000,
            "hash_v1",
            "hash_v2",
            False,
            True,
            CacheMissReason.PREFIX_CHANGED,
        ),
        # Normal match
        (
            "openai",
            2000,
            "hash_v1",
            "hash_v1",
            False,
            True,
            CacheMissReason.NONE,
        ),
    ],
)
def test_evaluate_cache_eligibility(
    policy_name: str,
    tokens: int,
    prev_hash: str | None,
    curr_hash: str | None,
    contaminated: bool,
    expected_eligible: bool,
    expected_reason: CacheMissReason,
) -> None:
    """Pre-flight eligibility check correctly attributes cache miss reasons."""
    policy = get_provider_cache_policy(policy_name)
    eligible, reason = evaluate_cache_eligibility(
        policy=policy,
        static_token_count=tokens,
        previous_prefix_hash=prev_hash,
        current_prefix_hash=curr_hash,
        has_contamination=contaminated,
    )
    assert eligible == expected_eligible
    assert reason == expected_reason


# ==============================================================================
# 2. AnthropicPromptCacheAdapter
# ==============================================================================


def test_anthropic_adapter_breakpoint_injection() -> None:
    """Anthropic adapter injects cache_control block when eligible, plain text when ineligible."""
    adapter = AnthropicPromptCacheAdapter()

    # Eligible request receives cache_control breakpoint
    req_eligible = adapter.prepare_request(
        static_prefix="You are an enterprise banking specialist.",
        dynamic_suffix="What is my balance?",
        model="claude-3-5-sonnet-20241022",
        is_eligible=True,
    )
    assert len(req_eligible["system"]) == 1
    sys_block = req_eligible["system"][0]
    assert sys_block["type"] == "text"
    assert sys_block["text"] == "You are an enterprise banking specialist."
    assert sys_block["cache_control"] == {"type": "ephemeral"}

    # Ineligible request (e.g. below token limit) does NOT receive cache_control
    req_ineligible = adapter.prepare_request(
        static_prefix="You are an enterprise banking specialist.",
        dynamic_suffix="What is my balance?",
        model="claude-3-5-sonnet-20241022",
        is_eligible=False,
    )
    assert len(req_ineligible["system"]) == 1
    assert "cache_control" not in req_ineligible["system"][0]


def test_anthropic_adapter_parse_usage() -> None:
    """Anthropic usage parser extracts cache_read, cache_creation, input, and output tokens."""
    adapter = AnthropicPromptCacheAdapter()
    raw_response = {
        "usage": {
            "cache_read_input_tokens": 1500,
            "cache_creation_input_tokens": 200,
            "input_tokens": 300,
            "output_tokens": 80,
        }
    }
    usage = adapter.parse_usage(raw_response)
    assert usage["cached_input_tokens"] == 1500
    assert usage["cache_write_tokens"] == 200
    assert usage["uncached_input_tokens"] == 300
    assert usage["output_tokens"] == 80


# ==============================================================================
# 3. OpenAIPromptCacheAdapter
# ==============================================================================


def test_openai_adapter_prepare_and_parse_usage() -> None:
    """OpenAI adapter formats system/user messages and computes uncached tokens correctly."""
    adapter = OpenAIPromptCacheAdapter()

    req = adapter.prepare_request(
        static_prefix="System prompt",
        dynamic_suffix="User prompt",
        model="gpt-4o",
        is_eligible=True,
    )
    assert req["model"] == "gpt-4o"
    assert req["messages"][0] == {"role": "system", "content": "System prompt"}
    assert req["messages"][1] == {"role": "user", "content": "User prompt"}

    raw_response = {
        "usage": {
            "prompt_tokens": 2000,
            "completion_tokens": 150,
            "prompt_tokens_details": {"cached_tokens": 1600},
        }
    }
    usage = adapter.parse_usage(raw_response)
    assert usage["cached_input_tokens"] == 1600
    assert usage["cache_write_tokens"] == 0
    # uncached = prompt_tokens (2000) - cached (1600) = 400
    assert usage["uncached_input_tokens"] == 400
    assert usage["output_tokens"] == 150


# ==============================================================================
# 4. Gemini, DeepSeek & Groq Adapters
# ==============================================================================


def test_gemini_adapter_prepare_and_parse_usage() -> None:
    """Gemini adapter structures systemInstruction and parses usageMetadata."""
    adapter = GeminiPromptCacheAdapter()
    req = adapter.prepare_request(
        static_prefix="Gemini static instruction",
        dynamic_suffix="User dynamic query",
        model="gemini-1.5-pro",
        is_eligible=True,
    )
    assert req["systemInstruction"] == {
        "parts": [{"text": "Gemini static instruction"}]
    }
    assert req["contents"] == [{"parts": [{"text": "User dynamic query"}]}]

    raw_response = {
        "usageMetadata": {
            "promptTokenCount": 40000,
            "cachedContentTokenCount": 35000,
            "candidatesTokenCount": 500,
        }
    }
    usage = adapter.parse_usage(raw_response)
    assert usage["cached_input_tokens"] == 35000
    assert usage["uncached_input_tokens"] == 5000
    assert usage["output_tokens"] == 500


def test_deepseek_adapter_parse_usage() -> None:
    """DeepSeek adapter extracts cached tokens from prompt_tokens_details."""
    adapter = DeepSeekPromptCacheAdapter()
    raw_response = {
        "usage": {
            "prompt_tokens": 500,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 300},
        }
    }
    usage = adapter.parse_usage(raw_response)
    assert usage["cached_input_tokens"] == 300
    assert usage["uncached_input_tokens"] == 200
    assert usage["output_tokens"] == 100


def test_groq_adapter_reports_zero_cached_tokens() -> None:
    """Groq adapter returns 0 cached tokens and full prompt count as uncached."""
    adapter = GroqPromptCacheAdapter()
    raw_response = {"usage": {"prompt_tokens": 800, "completion_tokens": 200}}
    usage = adapter.parse_usage(raw_response)
    assert usage["cached_input_tokens"] == 0
    assert usage["cache_write_tokens"] == 0
    assert usage["uncached_input_tokens"] == 800
    assert usage["output_tokens"] == 200


def test_get_provider_adapter_resolution() -> None:
    """get_provider_adapter returns correct adapter instance for provider/model."""
    assert isinstance(
        get_provider_adapter("claude-3-5-sonnet"), AnthropicPromptCacheAdapter
    )
    assert isinstance(get_provider_adapter("gpt-4o"), OpenAIPromptCacheAdapter)
    assert isinstance(get_provider_adapter("deepseek-chat"), DeepSeekPromptCacheAdapter)
    assert isinstance(get_provider_adapter("gemini-1.5-pro"), GeminiPromptCacheAdapter)
    assert isinstance(get_provider_adapter("groq"), GroqPromptCacheAdapter)
