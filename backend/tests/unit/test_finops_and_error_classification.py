"""Unit tests for FinOps pricing calculations, error classification, and secret sanitization.

Test Suite: UNIT-061
Target Areas:
- FinOps Pricing (app/finops/pricing.py)
  - calculate_baseline_cost across models, token bounds, and rounding precision
  - calculate_billed_cost with uncached, cached, write surcharges, and output tokens
  - calculate_provider_cache_savings with gross savings, Anthropic write surcharges, and negative savings
  - calculate_model_routing_savings with downgrades, upgrades (0.0), and identical models (0.0)
- Error Classification & Sanitization (app/providers/errors.py)
  - sanitize_error_message redacting DB URIs, private IPs, JWTs, Bearer/Basic headers, API keys, and key-value secrets
  - ProviderError hierarchy and string representation formatting
  - normalize_provider_error mapping across context limits, safety/policy, auth (401/403), quota vs rate limit (429), 402, 5xx unavailable, 408/timeout, 400 invalid request, and transport exceptions
"""

from __future__ import annotations

import httpx

from app.finops.pricing import (
    calculate_baseline_cost,
    calculate_billed_cost,
    calculate_model_routing_savings,
    calculate_provider_cache_savings,
    get_pricing,
)
from app.providers.errors import (
    ErrorCategory,
    ProviderAuthenticationError,
    ProviderContextLimitError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderPolicyError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    normalize_provider_error,
    sanitize_error_message,
)

# ============================================================================
# 1. FinOps Pricing Calculation Unit Tests
# ============================================================================


class TestFinOpsPricingCalculations:
    """Deterministic unit tests for pricing formulas and boundary conditions."""

    def test_get_pricing_known_and_fallback_models(self) -> None:
        """Known models return exact pricing; unknown models return default fallback."""
        gpt_pricing = get_pricing("gpt-4o")
        assert gpt_pricing.provider == "openai"
        assert gpt_pricing.input_per_million == 2.50
        assert gpt_pricing.output_per_million == 10.00

        claude_pricing = get_pricing("claude-3-5-sonnet")
        assert claude_pricing.provider == "anthropic"
        assert claude_pricing.cache_write_per_million == 3.75

        unknown_pricing = get_pricing("unknown-custom-model-xyz")
        assert unknown_pricing is not None
        assert unknown_pricing.input_per_million > 0

    def test_calculate_baseline_cost_standard(self) -> None:
        """Verify baseline cost formula: (in * in_rate + out * out_rate) / 1M."""
        # gpt-4o: $2.50/M input, $10.00/M output
        # 100,000 in ($0.25) + 20,000 out ($0.20) = $0.450000
        cost = calculate_baseline_cost(
            model="gpt-4o",
            raw_input_tokens=100_000,
            output_tokens=20_000,
        )
        assert cost == 0.45

    def test_calculate_baseline_cost_zero_and_negative_clamping(self) -> None:
        """Baseline cost clamps negative results to 0.0 and handles zero tokens."""
        assert calculate_baseline_cost("gpt-4o", 0, 0) == 0.0
        # Negative token counts (e.g. corrupted telemetry) are clamped to 0.0
        assert calculate_baseline_cost("gpt-4o", -100, -50) == 0.0

    def test_calculate_billed_cost_with_caching_and_writes(self) -> None:
        """Verify billed cost accounting with uncached, cached, write surcharge, and output."""
        # claude-3-5-sonnet:
        # in: $3.00, cache_read: $0.30, cache_write: $3.75, out: $15.00
        # 10k uncached ($0.030) + 50k cached ($0.015) + 10k write ($0.0375) + 5k out ($0.075)
        # total = 0.030 + 0.015 + 0.0375 + 0.075 = 0.157500
        cost = calculate_billed_cost(
            model="claude-3-5-sonnet",
            uncached_input_tokens=10_000,
            cached_input_tokens=50_000,
            cache_write_tokens=10_000,
            output_tokens=5_000,
        )
        assert cost == 0.1575

    def test_calculate_provider_cache_savings_zero_tokens(self) -> None:
        """Zero cached tokens returns 0.0."""
        assert calculate_provider_cache_savings("gpt-4o", cached_input_tokens=0) == 0.0
        assert (
            calculate_provider_cache_savings(
                "gpt-4o", cached_input_tokens=-10, cache_write_tokens=-5
            )
            == 0.0
        )

    def test_calculate_provider_cache_savings_non_anthropic(self) -> None:
        """Non-anthropic provider (e.g. OpenAI) has no write surcharge above input rate."""
        # gpt-4o: input $2.50, cache_read $1.25 -> savings $1.25 per 1M tokens
        # 200,000 cached tokens -> 200_000 * 1.25 / 1M = $0.25
        savings = calculate_provider_cache_savings(
            "gpt-4o",
            cached_input_tokens=200_000,
            cache_write_tokens=50_000,  # cache_write <= input_per_million so surcharge is 0
        )
        assert savings == 0.25

    def test_calculate_provider_cache_savings_anthropic_write_surcharge(self) -> None:
        """Anthropic cache creation incurs extra surcharge: (3.75 - 3.00) = $0.75/1M."""
        # 100,000 read ($3.00 - $0.30 = $2.70/1M) -> gross $0.27
        # 20,000 write surcharge -> 20,000 * 0.75 / 1M = $0.015
        # net savings = 0.27 - 0.015 = $0.255
        savings = calculate_provider_cache_savings(
            "claude-3-5-sonnet",
            cached_input_tokens=100_000,
            cache_write_tokens=20_000,
        )
        assert savings == 0.255

    def test_calculate_provider_cache_savings_negative_when_writes_dominate(
        self,
    ) -> None:
        """When writing cache with zero reads, net savings is negative (cost surcharge)."""
        # 0 read, 10,000 write -> surcharge = 10,000 * 0.75 / 1M = $0.0075 -> net = -0.0075
        savings = calculate_provider_cache_savings(
            "claude-3-5-sonnet",
            cached_input_tokens=0,
            cache_write_tokens=10_000,
        )
        assert savings == -0.0075

    def test_calculate_model_routing_savings_same_model(self) -> None:
        """Routing to the identical model yields 0.0 savings."""
        assert calculate_model_routing_savings("gpt-4o", "gpt-4o", 10_000, 1_000) == 0.0
        # Case insensitive match
        assert (
            calculate_model_routing_savings("GPT-4o", " gpt-4o ", 10_000, 1_000) == 0.0
        )

    def test_calculate_model_routing_savings_downgrade(self) -> None:
        """Routing to a cheaper model yields positive dollar savings."""
        # gpt-4o: in $2.50, out $10.00
        # gpt-4o-mini: in $0.15, out $0.60
        # 100k in: gpt-4o = 0.25, gpt-4o-mini = 0.015 -> diff = 0.235
        # 10k out: gpt-4o = 0.10, gpt-4o-mini = 0.006 -> diff = 0.094
        # total savings = 0.235 + 0.094 = 0.329
        savings = calculate_model_routing_savings(
            requested_model="gpt-4o",
            selected_model="gpt-4o-mini",
            input_tokens=100_000,
            output_tokens=10_000,
        )
        assert savings == 0.329

    def test_calculate_model_routing_savings_upgrade_returns_zero(self) -> None:
        """Routing to a more expensive model (upgrade) yields 0.0 savings (not negative)."""
        savings = calculate_model_routing_savings(
            requested_model="gpt-4o-mini",
            selected_model="gpt-4o",
            input_tokens=100_000,
            output_tokens=10_000,
        )
        assert savings == 0.0


# ============================================================================
# 2. Secret Sanitization Unit Tests
# ============================================================================


class TestSecretSanitization:
    """Unit tests verifying zero secret/credential leakage in error messages."""

    def test_sanitize_database_connection_uris(self) -> None:
        """Redacts Postgres, MySQL, Redis, MongoDB, and AMQP connection strings with credentials."""
        uris = [
            "Failed connecting to postgresql://postgres:SuperSecret123@db.prod.internal:5432/main",
            "Error on mysql://root:admin_pass@localhost:3306/users",
            "redis://default:s3cr3tP@ss@10.0.1.5:6379/0 connection lost",
            "mongodb+srv://admin:clusterKey99@cluster0.mongodb.internal/app failed",
            "amqp://guest:guest123@rabbitmq.internal:5672/vhost error",
        ]
        for uri in uris:
            sanitized = sanitize_error_message(uri)
            assert "[REDACTED_SECRET]" in sanitized
            assert "SuperSecret123" not in sanitized
            assert "admin_pass" not in sanitized
            assert "s3cr3tP@ss" not in sanitized
            assert "clusterKey99" not in sanitized
            assert "guest123" not in sanitized

    def test_sanitize_private_ip_addresses(self) -> None:
        """Redacts private RFC1918 IP addresses with or without ports."""
        ips = [
            "Connection refused to 10.0.1.25:8000",
            "Host unreachable: 172.20.14.5:9090",
            "Timeout contacting 192.168.1.100",
        ]
        for msg in ips:
            sanitized = sanitize_error_message(msg)
            assert "[REDACTED_SECRET]" in sanitized
            assert "10.0.1.25" not in sanitized
            assert "172.20.14.5" not in sanitized
            assert "192.168.1.100" not in sanitized

    def test_sanitize_jwt_and_auth_headers(self) -> None:
        """Redacts JWTs, Bearer tokens, and Basic auth tokens."""
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        msg = f"Unauthorized token {jwt} with Bearer sk-bearer-token-123456"
        sanitized = sanitize_error_message(msg)
        assert jwt not in sanitized
        assert "sk-bearer-token-123456" not in sanitized
        assert "[REDACTED_SECRET]" in sanitized

    def test_sanitize_provider_api_keys(self) -> None:
        """Redacts OpenAI (sk-), Anthropic (sk-ant-), Google (AIza), GitHub (ghp_), and AWS (AKIA) keys."""
        keys_msg = (
            "API failure with sk-proj-1234567890abcdef and "
            "sk-ant-api03-abcdef1234567890 and "
            "AIzaSyB1234567890abcdef1234567890 and "
            "ghp_1234567890abcdef1234567890abcdef1234 and "
            "AKIAIOSFODNN7EXAMPLE"
        )
        sanitized = sanitize_error_message(keys_msg)
        assert "sk-proj-1234567890abcdef" not in sanitized
        assert "sk-ant-api03-abcdef1234567890" not in sanitized
        assert "AIzaSyB1234567890abcdef1234567890" not in sanitized
        assert "ghp_1234567890abcdef1234567890abcdef1234" not in sanitized
        assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
        assert sanitized.count("[REDACTED_SECRET]") >= 5

    def test_sanitize_key_value_assignments(self) -> None:
        """Redacts key-value secret pairs like api_key='...', password=..., x-api-key: ..."""
        msg = "Error setting api_key='secret-val-12345', password=\"superpass99\", x-api-key: sensitive-header-val"
        sanitized = sanitize_error_message(msg)
        assert "secret-val-12345" not in sanitized
        assert "superpass99" not in sanitized
        assert "sensitive-header-val" not in sanitized


# ============================================================================
# 3. Provider Error Hierarchy Unit Tests
# ============================================================================


class TestProviderErrorHierarchy:
    """Tests for ProviderError base and specialized exception classes."""

    def test_provider_error_str_formatting(self) -> None:
        """Verifies canonical string format: [provider] CATEGORY (HTTP code) model=...: message."""
        err = ProviderError(
            message="Connection failed",
            provider="openai",
            category=ErrorCategory.RETRYABLE,
            model="gpt-4o",
            status_code=503,
            is_retryable=True,
        )
        assert (
            str(err) == "[openai] RETRYABLE (HTTP 503) model=gpt-4o : Connection failed"
        )

    def test_provider_error_message_is_sanitized_on_init(self) -> None:
        """ProviderError automatically scrubs secrets in its message upon instantiation."""
        err = ProviderError(
            message="Failed using key sk-1234567890abcdef",
            provider="openai",
            category=ErrorCategory.NON_RETRYABLE,
        )
        assert "sk-1234567890abcdef" not in err.message
        assert "[REDACTED_SECRET]" in err.message

    def test_specialized_subclasses_defaults(self) -> None:
        """Verifies category, retryability, and default status codes across error subclasses."""
        auth_err = ProviderAuthenticationError("Auth failed", "anthropic")
        assert auth_err.category == ErrorCategory.AUTHENTICATION
        assert auth_err.is_retryable is False
        assert auth_err.status_code == 401

        quota_err = ProviderQuotaError("Quota exceeded", "openai")
        assert quota_err.category == ErrorCategory.QUOTA
        assert quota_err.is_retryable is False
        assert quota_err.status_code == 429

        ctx_err = ProviderContextLimitError("Context limit", "gemini")
        assert ctx_err.category == ErrorCategory.CONTEXT_LIMIT
        assert ctx_err.is_retryable is False
        assert ctx_err.status_code == 400

        unavail_err = ProviderUnavailableError("Down", "groq", retry_after_seconds=2.5)
        assert unavail_err.category == ErrorCategory.PROVIDER_UNAVAILABLE
        assert unavail_err.is_retryable is True
        assert unavail_err.status_code == 503
        assert unavail_err.retry_after_seconds == 2.5

        rate_err = ProviderRateLimitError(
            "Too many reqs", "deepseek", retry_after_seconds=5.0
        )
        assert rate_err.category == ErrorCategory.RETRYABLE
        assert rate_err.is_retryable is True
        assert rate_err.status_code == 429

        policy_err = ProviderPolicyError("Safety triggered", "gemini")
        assert policy_err.category == ErrorCategory.POLICY_REJECTED
        assert policy_err.is_retryable is False
        assert policy_err.status_code == 400

        timeout_err = ProviderTimeoutError("Read timed out", "openrouter")
        assert timeout_err.category == ErrorCategory.RETRYABLE
        assert timeout_err.is_retryable is True
        assert timeout_err.status_code == 408

        invalid_err = ProviderInvalidRequestError("Bad schema", "openai")
        assert invalid_err.category == ErrorCategory.NON_RETRYABLE
        assert invalid_err.is_retryable is False
        assert invalid_err.status_code == 400


# ============================================================================
# 4. Normalize Provider Error Function Unit Tests
# ============================================================================


class TestNormalizeProviderError:
    """Tests for normalize_provider_error mapping across status codes, response bodies, and exceptions."""

    def test_normalize_context_limit_keywords(self) -> None:
        """Recognizes context limit errors across various provider phrasing."""
        phrases = [
            "This model's maximum context length is 128000 tokens",
            "Prompt exceeds token limit of 8192",
            "too many tokens in request",
            "prompt is too long for this endpoint",
        ]
        for phrase in phrases:
            err = normalize_provider_error(
                provider="openai",
                status_code=400,
                response_body={"error": {"message": phrase}},
                model="gpt-4o",
            )
            assert isinstance(err, ProviderContextLimitError)
            assert err.category == ErrorCategory.CONTEXT_LIMIT
            assert err.is_retryable is False

    def test_normalize_policy_and_safety_keywords(self) -> None:
        """Recognizes policy and safety moderation blocks."""
        phrases = [
            "Request blocked by safety filters",
            "Content violation detected by harm_category",
            "moderation triggered policy violation",
        ]
        for phrase in phrases:
            err = normalize_provider_error(
                provider="gemini",
                status_code=400,
                response_body={"error": {"message": phrase}},
            )
            assert isinstance(err, ProviderPolicyError)
            assert err.category == ErrorCategory.POLICY_REJECTED
            assert err.is_retryable is False

    def test_normalize_authentication_status_codes(self) -> None:
        """Status codes 401 and 403 map to ProviderAuthenticationError."""
        for code in (401, 403):
            err = normalize_provider_error(
                provider="anthropic",
                status_code=code,
                response_body={"error": {"message": "Invalid API key"}},
            )
            assert isinstance(err, ProviderAuthenticationError)
            assert err.category == ErrorCategory.AUTHENTICATION
            assert err.is_retryable is False

    def test_normalize_429_quota_vs_rate_limit(self) -> None:
        """Status 429 with quota keywords maps to ProviderQuotaError; otherwise ProviderRateLimitError."""
        # Quota keywords
        quota_err = normalize_provider_error(
            provider="openai",
            status_code=429,
            response_body={
                "error": {
                    "message": "You exceeded your current quota, please check your plan and billing details."
                }
            },
        )
        assert isinstance(quota_err, ProviderQuotaError)
        assert quota_err.category == ErrorCategory.QUOTA
        assert quota_err.is_retryable is False

        # Concurrency / rate limit
        rate_err = normalize_provider_error(
            provider="openai",
            status_code=429,
            response_body={
                "error": {"message": "Rate limit reached for requests per minute"}
            },
            retry_after=3.5,
        )
        assert isinstance(rate_err, ProviderRateLimitError)
        assert rate_err.category == ErrorCategory.RETRYABLE
        assert rate_err.is_retryable is True
        assert rate_err.retry_after_seconds == 3.5

    def test_normalize_402_payment_required(self) -> None:
        """Status 402 maps to ProviderQuotaError."""
        err = normalize_provider_error(
            provider="deepseek",
            status_code=402,
            response_body="Insufficient balance",
        )
        assert isinstance(err, ProviderQuotaError)
        assert err.status_code == 402

    def test_normalize_5xx_unavailable_codes(self) -> None:
        """502, 503, 504, 529 map to ProviderUnavailableError."""
        for code in (502, 503, 504, 529):
            err = normalize_provider_error(
                provider="groq",
                status_code=code,
                response_body="Bad Gateway or Overloaded",
                retry_after=1.0,
            )
            assert isinstance(err, ProviderUnavailableError)
            assert err.category == ErrorCategory.PROVIDER_UNAVAILABLE
            assert err.is_retryable is True

    def test_normalize_timeout_status_and_message(self) -> None:
        """Status 408 or keyword 'timeout' maps to ProviderTimeoutError."""
        err_code = normalize_provider_error(
            provider="anthropic",
            status_code=408,
            response_body="Request Timeout",
        )
        assert isinstance(err_code, ProviderTimeoutError)

        err_msg = normalize_provider_error(
            provider="anthropic",
            status_code=500,
            response_body="Gateway connection timeout after 30s",
        )
        assert isinstance(err_msg, ProviderTimeoutError)

    def test_normalize_400_invalid_request(self) -> None:
        """Status 400 without context or policy terms maps to ProviderInvalidRequestError."""
        err = normalize_provider_error(
            provider="openai",
            status_code=400,
            response_body={
                "error": {"message": "Invalid parameter: temperature must be <= 2.0"}
            },
        )
        assert isinstance(err, ProviderInvalidRequestError)
        assert err.category == ErrorCategory.NON_RETRYABLE
        assert err.is_retryable is False

    def test_normalize_transport_and_network_exceptions(self) -> None:
        """Network/connect/dns transport exceptions map to ProviderUnavailableError."""
        exc = httpx.ConnectError("Failed to establish connection to api.anthropic.com")
        err = normalize_provider_error(
            provider="anthropic",
            status_code=None,
            exc=exc,
        )
        assert isinstance(err, ProviderUnavailableError)
        assert err.is_retryable is True

    def test_normalize_unknown_fallback(self) -> None:
        """Unrecognized error fallback returns base ProviderError with NON_RETRYABLE category."""
        err = normalize_provider_error(
            provider="custom_llm",
            status_code=418,
            response_body="I'm a teapot",
        )
        assert type(err) is ProviderError
        assert err.category == ErrorCategory.NON_RETRYABLE
        assert err.is_retryable is False
