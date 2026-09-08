# REPAIR-02 — TOK-02 CANONICAL TOKEN ACCOUNTING

Finding:
TOK-02

Priority:
CRITICAL

Objective:
Make token accounting reflect the actual model-visible input envelope.

Current defect to verify:
Gateway token accounting is based primarily on last_user_msg.

Required invariant:

Recorded prompt usage must represent all relevant model-visible input:

- system
- conversation history
- user query
- tools
- RAG context when present

Required accounting dimensions:

- raw_input_tokens
- optimized_input_tokens
- provider_cached_input_tokens
- completion_tokens
- physical_tokens_pruned
- response_cache_avoided_tokens
- effective_billed_tokens

Final usage should use provider-reported usage for reconciliation when available.

Required tests:

Given:
system = 2000
history = 3000
query = 50

the accounting layer must not report raw input as 50.

Also test:
- tools
- RAG context
- optimized context
- provider cache telemetry
- response cache hit

Forbidden:

Do not introduce a second accounting system.
Do not repair TOK-01 as a separate concern.

Definition of done:
Accounting reflects model-visible semantics and regression tests prove it.

==================================================
ACTUAL EXECUTION RESULT
==================================================

STATUS:
COMPLETED

ROOT CAUSE:
1. AI Gateway Prompt Envelope Truncation: In `backend/app/services/ai_gateway.py` (`chat_completions` and `chat_completions_stream`), token accounting for incoming requests historically extracted only `last_user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), "")` and estimated prompt tokens exclusively via `estimate_tokens(last_user_msg)`. This ignored system instructions, multi-turn conversation history, assistant tool calls, tool results, JSON tool schemas, and RAG context chunks. For example, a request with 2,000 system tokens, 3,000 dialogue history tokens, and 50 user query tokens was collapsed and billed as ~50 tokens instead of ~5,050 tokens.
2. Incomplete Accounting Dimensions: The canonical ledger `TokenAccounting` (`backend/app/optimizer/token_accounting.py`) historically used legacy terminology (`raw_prompt_tokens`, `pruned_prompt_tokens`, `actual_billed_tokens`) and lacked explicit fields for canonical dimensions: `raw_input_tokens`, `optimized_input_tokens`, `provider_cached_input_tokens`, `physical_tokens_pruned`, `response_cache_avoided_tokens`, `effective_billed_tokens`, and provider reconciliation status (`reconciled_with_provider`).
3. Disconnected Upstream Provider Reconciliation: When upstream LLM providers returned actual telemetry (`ProviderCacheTelemetry`), usage was not reconciled back into the canonical `TokenUsageRecord`, leaving provider-side prompt cache hits unrecorded or disconnected from FinOps billing.
4. Tier 1 Cache Hit Envelope Under-accounting: On Tier 1 semantic/exact cache hits in `ai_gateway.py`, `tokens_saved` fell back to cached entry values or single prompt estimates rather than crediting the caller for avoiding the entire model-visible prompt envelope.

INVARIANT:
1. Model-Visible Envelope Integrity: Recorded prompt usage (`raw_input_tokens`) must account for all model-visible input:
   - System/developer instructions
   - Multi-turn conversation history (user, assistant, tool results, tool calls)
   - User query
   - Tools JSON schemas
   - RAG context chunks
   - Dynamic prompt suffixes
2. Conservation of Tokens: Across all optimization and caching layers:
   - `raw_input_tokens == optimized_input_tokens + physical_tokens_pruned`
   - `baseline_total == effective_billed_tokens + tokens_saved`
   - `tokens_saved == physical_tokens_pruned + provider_cached_input_tokens + response_cache_avoided_tokens`
3. Bidirectional Backward Compatibility: Full compatibility is preserved with legacy fields (`raw_prompt_tokens`, `pruned_prompt_tokens`, `actual_billed_tokens`, `provider_cached_tokens`) via bidirectional validation in `TokenUsageRecord`.
4. Provider Reconciliation: When upstream provider telemetry (`ProviderCacheTelemetry`) is present and reports non-zero usage, the canonical record reconciles with provider ground truth (`reconciled_with_provider=True`). If provider reports 0 tokens (e.g. streaming or mocked provider), fallback preserves the local model-visible envelope calculation.
5. Single Canonical Ledger: All accounting flows through `TokenAccounting` without creating secondary ledgers or parallel accounting systems.
6. Multi-Backend Quota Governance: `QuotaManager.get_tokens_saved` and `QuotaManager.record_tokens_saved` operate atomically across both distributed Redis infrastructure and standalone in-memory execution.

CHANGES:
1. Canonical Accounting Dimensions in `backend/app/optimizer/token_accounting.py`:
   - Added canonical fields to `TokenUsageRecord`: `raw_input_tokens`, `optimized_input_tokens`, `provider_cached_input_tokens`, `physical_tokens_pruned`, `response_cache_avoided_tokens`, `effective_billed_tokens`, and `reconciled_with_provider`.
   - Added `@model_validator(mode="before")` `_sync_dimensions` ensuring 100% bidirectional synchronization between canonical fields and legacy fields (`raw_prompt_tokens`, `pruned_prompt_tokens`, `actual_billed_tokens`, `provider_cached_tokens`).
   - Implemented `TokenAccounting.calculate_envelope_tokens(...)` calculating exact model-visible tokens across all messages (including content, role framing overhead, tool_calls, and tool results), tool schemas, explicit system prompts, RAG context, and dynamic suffixes.
   - Updated `TokenAccounting.record_transaction(...)` to support canonical dimensions and perform telemetry reconciliation against `ProviderCacheTelemetry`.
2. AI Gateway Integration in `backend/app/services/ai_gateway.py`:
   - In `GatewayInferenceProxy.chat_completions`: replaced `estimate_tokens(last_user_msg)` with `TokenAccounting.calculate_envelope_tokens(...)` for both Tier 1 cache hit and cache miss paths. Reconciled usage with `upstream_response.telemetry`, deducted quota using `record.actual_billed_tokens - record.completion_tokens`, and reported canonical dimensions to FinOps.
   - In `GatewayInferenceProxy.chat_completions_stream`: replaced `estimate_tokens(last_user_msg)` with `calculate_envelope_tokens(...)` for cache hit and miss paths, ensuring stream quota deductions and cache hit `tokens_saved` reflect the entire prompt envelope.
   - Added `QuotaManager.get_tokens_saved(...)` with Redis-backed atomic reads and fallback to memory.
3. Unit & Integration Test Suite in `backend/tests/unit/test_canonical_token_accounting.py`:
   - Implemented 16 comprehensive tests covering envelope calculation (> 5050 tokens vs 50 tokens), tools schema accounting, RAG context chunks, two-zone optimized prompt tokens, provider cache telemetry reconciliation, provider reconciliation fallback on 0 tokens, Tier 1 cache hit accounting, conservation of tokens invariant, bidirectional backward compatibility, Gateway chat_completions integration, Gateway cache hit integration, Gateway streaming integration, Gateway streaming cache hit integration, assistant tool calls & tool results envelope calculation, QuotaManager Redis and memory resolution, and FinOps cost reconciliation.

MODIFIED FILES:
- `backend/app/optimizer/token_accounting.py`
- `backend/app/services/ai_gateway.py`
- `backend/tests/unit/test_canonical_token_accounting.py`
- `docs/repair/R/REPAIR-02 — TOK-02 Canonical Token Accounting.md`

TESTS ADDED OR CHANGED:
- `backend/tests/unit/test_canonical_token_accounting.py` (16 tests):
  1. `test_system_history_query_envelope_accounting`: Verifies 2000 system + 3000 history + 50 query is accounted as ~5050 tokens, NOT 50 tokens.
  2. `test_accounting_with_tools_schema`: Verifies tool definitions JSON schemas are counted in `raw_input_tokens`.
  3. `test_accounting_with_rag_context`: Verifies RAG context passages are accounted in `raw_input_tokens`.
  4. `test_accounting_with_optimized_context`: Verifies two-zone optimization calculates `physical_tokens_pruned` and `tokens_saved`.
  5. `test_provider_cache_telemetry_reconciliation`: Verifies reconciliation with `ProviderCacheTelemetry` (cached vs uncached prompt tokens).
  6. `test_provider_reconciliation_zero_tokens_fallback`: Verifies fallback preserves local envelope tokens when provider telemetry reports 0 tokens.
  7. `test_exact_cache_hit_accounting`: Verifies Tier 1 cache hit credits the full envelope for `response_cache_avoided_tokens` and `tokens_saved`.
  8. `test_token_conservation_invariant_miss_and_hit`: Verifies conservation law `baseline == effective_billed + tokens_saved` across cache hit and miss.
  9. `test_token_usage_record_backward_compatibility`: Verifies bidirectional synchronization between legacy and canonical dimension names.
  10. `test_gateway_chat_completions_full_envelope_accounting`: E2E Gateway test verifying non-streaming completions report > 1000 tokens for multi-turn requests.
  11. `test_gateway_chat_completions_cache_hit_accounting`: E2E Gateway test verifying Tier 1 cache hit reports > 1000 tokens saved for multi-turn requests.
  12. `test_gateway_chat_completions_stream_accounting`: E2E Gateway test verifying streaming quota deduction accounts the multi-turn envelope.
  13. `test_gateway_chat_completions_stream_cache_hit_accounting`: E2E Gateway test verifying streaming cache hit accounts the full envelope in quota manager.
  14. `test_accounting_with_assistant_tool_calls_and_tool_results`: Verifies assistant tool_calls and role='tool' results are included in envelope calculation.
  15. `test_quota_manager_get_tokens_saved_redis_and_memory`: Verifies `QuotaManager.get_tokens_saved` across Redis, Redis failure fallback, and in-memory paths.
  16. `test_finops_integration_with_canonical_dimensions`: Verifies FinOps cost settlement receives canonical token usage.

TESTS AND CHECKS ACTUALLY EXECUTED:
1. Focused Canonical Token Accounting Suite:
   - Command: `python -m pytest tests/unit/test_canonical_token_accounting.py -v`
   - Result: 16 passed in 3.30s.
2. AI Gateway Integration Suite:
   - Command: `python -m pytest tests/test_gateway.py tests/unit/test_canonical_token_accounting.py -v`
   - Result: 33 passed in 6.17s.
3. Subsystem & Optimization Regression Suite:
   - Command: `python -m pytest tests/evals/test_token_benchmark.py tests/test_finops_accounting.py tests/test_cache_identity.py tests/unit/test_structured_conversation_contract.py tests/test_commercial_services.py tests/test_provider_prompt_caching.py -v`
   - Result: 96 passed.
4. Contract & Agent Architecture Suite:
   - Command: `python -m pytest tests/test_api_contract.py tests/test_internal_mutual_auth.py tests/test_agent_platform.py tests/test_multi_agent.py -v`
   - Result: 41 passed.
5. Code Quality (Linter & Formatter):
   - Command: `ruff check app/ tests/unit/test_canonical_token_accounting.py` -> All checks passed!
   - Command: `ruff format --check app/ tests/unit/test_canonical_token_accounting.py` -> 142 files already formatted.
6. Type Checking:
   - Command: `mypy app/services/ai_gateway.py app/optimizer/token_accounting.py` -> Success: no issues found in 2 source files.
7. Security Scan:
   - Command: `bandit -r app/optimizer/token_accounting.py app/services/ai_gateway.py` -> 0 issues identified.
8. OpenAPI Contract Compatibility:
   - Command: `python scripts/check_openapi_breaking_changes.py` -> 0 breaking changes detected. Status: 100% Backward Compatible.

CI VERIFICATION:
- GitHub Actions Run ID: `34282511464`
- Commit SHA: `1e4f14fa76b7dbf3d2fbcbbec6765bc2f2053181`
- Branch: `feat/repair-02-canonical-token-accounting`
- Pull Request: #24 (`https://github.com/NguyenQuan121321/JakeAI/pull/24`)
- Overall Status: `completed`
- Overall Conclusion: `success`
- Job Breakdown:
  1. `Code Quality & Type Analysis (3.12)`: completed - success
  2. `Infrastructure & Workflow Linting`: completed - success
  3. `DevSecOps - Secret & Key Leak Detection`: completed - success
  4. `DevSecOps - Vulnerability Audit, SAST & License Compliance`: completed - success
  5. `Frontend Widget Build & Quality Verification`: completed - success
  6. `Code Quality & Type Analysis (3.11)`: completed - success
  7. `Automated Tests & AI RAG Regression (3.12)`: completed - success
  8. `Automated Tests & AI RAG Regression (3.11)`: completed - success (strict branch coverage >= 85%, patch coverage diff >= 80%, token benchmark gate >= 40%, portfolio benchmark >= 40%)
  9. `Container Packaging & Vulnerability Scan`: completed - success

ACCEPTANCE CRITERIA STATUS:
- [x] Recorded prompt usage represents all model-visible input (system, conversation history, user query, tools, RAG context).
- [x] Canonical accounting dimensions present and populated:
      `raw_input_tokens`, `optimized_input_tokens`, `provider_cached_input_tokens`, `completion_tokens`, `physical_tokens_pruned`, `response_cache_avoided_tokens`, `effective_billed_tokens`.
- [x] Reconciliation with upstream provider telemetry (`ProviderCacheTelemetry`) implemented with non-zero fallback.
- [x] Test case (system=2000, history=3000, query=50 -> raw input ~5050 tokens != 50 tokens) passing and verified.
- [x] Single canonical ledger maintained without secondary accounting systems.
- [x] TOK-01 (canonical tokenizer adoption) left isolated for REPAIR-14.
- [x] No CI checks, linters, or coverage thresholds weakened or bypassed.

SECURITY & TENANT ISOLATION:
- Tenant isolation is strictly preserved in quota management and Redis keys (`gateway:usage:{tenant_id}:{period}` and `gateway:tokens_saved:{tenant_id}:{period}`).
- No API keys, BYOK credentials, or secrets are exposed in logs or telemetry records.

REMAINING ISSUES:
- None for REPAIR-02.

RISKS:
- Provider prompt token counts from downstream models may differ slightly from local character/word estimations when provider telemetry is unavailable. Provider telemetry reconciliation ensures exact upstream billing alignment when available.

NEXT TASK:
- REPAIR-03 — DUP-02 Canonical Provider Resolution