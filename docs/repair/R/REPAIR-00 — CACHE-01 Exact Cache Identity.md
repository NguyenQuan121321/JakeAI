# REPAIR-00 — CACHE-01 EXACT CACHE IDENTITY

Finding:
CACHE-01

Priority:
CRITICAL

Objective:
Repair exact response cache identity so semantically different inference requests cannot collide.

Evidence to verify:
The gateway currently derives exact cache access from the last user message and does not provide the complete generation identity.

Required invariant:

Requests MUST NOT share an exact response-cache identity when any generation-relevant dimension differs.

Evaluate at minimum:

- tenant
- provider
- model
- system instructions
- complete message history
- tools
- response format
- meaningful generation parameters
- cache schema/version

Equivalent requests MUST produce equivalent canonical cache identities.

Required work:

1. Inspect the complete cache lookup path.
2. Inspect cache write path.
3. Inspect semantic/exact cache matching rules.
4. Add regression tests that fail under the current implementation.
5. Implement canonical cache identity.
6. Ensure canonical serialization is deterministic.
7. Version the cache identity.
8. Preserve tenant isolation.
9. Handle legacy cache entries safely.
10. Run focused and relevant tests.

Required regression scenarios:

- same request => same identity
- different model => different identity
- different provider => different identity
- different system prompt => different identity
- different conversation history => different identity
- different tools => different identity
- different meaningful generation parameters => different identity

Forbidden:

Do not repair PROV-02, TOK-02, or DUP-02 as independent tasks.

Do not redesign semantic caching unrelated to this defect.

Definition of done:

Cache collision regression tests pass.
Existing cache tests pass.
Relevant static checks pass.
No security regression.
Final diff remains scoped to CACHE-01.

==================================================
ACTUAL EXECUTION RESULT
==================================================

STATUS:
COMPLETED

ROOT CAUSE:
In `GatewayInferenceProxy.chat_completions` and `chat_completions_stream` (`backend/app/services/ai_gateway.py`), exact cache lookups historically extracted only `last_user_msg` and invoked `cache_mgr.get(last_user_msg, tenant_id=tenant_id)` without passing `model`, `provider`, `system_instructions`, `messages` (complete history), `tools`, `response_format`, or `generation_params`. In `backend/app/optimizer/semantic_cache.py`, the legacy hashing function `_compute_hash` only hashed `text`, `tenant_id`, `model`, `provider`, and `version`, omitting system instructions, multi-turn history, tools, response format, and execution parameters. Furthermore, permissive fallback matching in the exact cache layer permitted cross-model/provider collisions when defaults were used, and unconstrained Tier 2 semantic fallback allowed identical prompt strings under differing system instructions or tools to hit cached responses.

INVARIANT:
Requests MUST NOT share an exact response-cache identity when any generation-relevant dimension differs. Evaluated dimensions: tenant, provider, model, system instructions, complete message history, tools, response format, meaningful generation parameters, cache schema version (`v2.0`). Equivalent requests MUST produce equivalent canonical cache identities.

CHANGES:
1. Implemented `compute_cache_identity` in `backend/app/optimizer/semantic_cache.py`: computes a canonical SHA-256 digest over normalized and deterministically sorted representations of: version (`v2.0`), tenant, provider, model, system instructions (NFC-normalized, whitespace-collapsed), complete message history (`role:content` joined by ASCII record separator `\x1e`), tool schemas (JSON with sorted keys), response format constraints, and non-null generation parameters (JSON with sorted keys), joined by ASCII unit separator `\x1f`.
2. Bumped cache schema version to `v2.0` (`CACHE_VERSION = "v2.0"`), ensuring all legacy unkeyed or v1.0 entries are isolated and cannot collide.
3. Extended `SemanticCacheEntry` with `system_instructions`, `tools`, and `response_format` fields with default values for full backward compatibility.
4. Added `exact_only` parameter to `SemanticCacheManager.get(...)` to allow callers (such as the AI Gateway Tier 1 exact cache) to bypass Tier 2 semantic vector search, and added explicit guardrails in Tier 2 to reject matches with conflicting system instructions, tools, or response formats.
5. Extended `GatewayChatRequest` in `backend/app/services/ai_gateway.py` to support `tools` and `response_format`.
6. Updated `GatewayInferenceProxy.chat_completions` and `chat_completions_stream` in `backend/app/services/ai_gateway.py` to extract system instructions, full message history, generation parameters, resolved provider, tools, and response format, passing all dimensions with `exact_only=True` to `cache_mgr.get` and `cache_mgr.set`.
7. Retained legacy `_compute_hash` for backward compatibility with external callers.

MODIFIED FILES:
- `backend/app/optimizer/semantic_cache.py`
- `backend/app/services/ai_gateway.py`
- `backend/tests/unit/test_cache_identity.py`
- `docs/repair/R/REPAIR-00 — CACHE-01 Exact Cache Identity.md`

TESTS ADDED OR CHANGED:
- `backend/tests/unit/test_cache_identity.py` (29 comprehensive test cases):
  - `TestComputeCacheIdentity`:
    - `test_same_request_same_identity`: Identical requests produce identical 64-char SHA-256 hash.
    - `test_different_model_different_identity`: Different model => different identity.
    - `test_different_provider_different_identity`: Different provider => different identity.
    - `test_different_system_prompt_different_identity`: Different system prompt => different identity.
    - `test_different_conversation_history_different_identity`: Different message history => different identity.
    - `test_different_message_order_different_identity`: Different message ordering => different identity.
    - `test_different_tools_different_identity`: Different tools => different identity.
    - `test_different_response_format_different_identity`: Different response format => different identity.
    - `test_response_format_key_order_invariance`: Dict key order invariance for response format.
    - `test_different_generation_params_different_identity`: Different temperature => different identity.
    - `test_different_max_tokens_different_identity`: Different max_tokens => different identity.
    - `test_different_tenant_different_identity`: Strict tenant isolation.
    - `test_different_version_different_identity`: Schema version bump changes identity.
    - `test_whitespace_normalization`: Whitespace collapsing and Unicode NFC normalization.
    - `test_tool_key_order_invariance`: Dict key order invariance for tool schemas.
    - `test_empty_messages_vs_no_messages`: Deterministic distinction between empty and absent messages.
    - `test_same_last_message_different_system_prompt_no_collision`: Verification of audit scenario.
    - `test_same_last_message_different_model_no_collision`: Verification of audit scenario.
  - Integration Tests (`SemanticCacheManager`):
    - `test_cache_miss_different_model`: Cache miss when model differs.
    - `test_cache_miss_different_provider`: Cache miss when provider differs.
    - `test_cache_miss_different_system_prompt`: Cache miss when system prompt differs.
    - `test_cache_miss_different_history`: Cache miss when history differs.
    - `test_cache_miss_different_tools`: Cache miss when tools differ.
    - `test_cache_miss_different_response_format`: Cache miss when response format differs.
    - `test_cache_miss_different_generation_params`: Cache miss when temperature differs.
    - `test_cache_hit_identical_request`: Cache hit when all dimensions match.
    - `test_cache_backward_compatibility`: Legacy single-prompt callers still function.
    - `test_legacy_compute_hash_still_works`: Legacy hash function remains operational.
  - End-to-End Gateway Integration Test:
    - `test_gateway_exact_cache_isolation_across_dimensions`: Full `GatewayInferenceProxy.chat_completions` verification proving exact cache hits for identical requests and exact cache misses across models, system prompts, tools, response formats, and tenants.

TESTS AND CHECKS ACTUALLY EXECUTED:
1. Unit regression tests:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_cache_identity.py -v` -> 29 passed in 8.90s.
2. Existing cache tests:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_semantic_cache.py -v` -> 4 passed in 1.54s.
3. Related subsystem tests:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_provider_prompt_caching.py backend/tests/test_harmonization.py backend/tests/evals/test_phase03_token_optimization.py -v` -> 28 passed in 4.93s.
4. Full repository test suite:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests` -> 340 passed, 1 warning in 107.08s.
5. Static code analysis & linting:
   `backend\.venv\Scripts\python.exe -m ruff check backend/` -> All checks passed.
6. Code style & formatting:
   `backend\.venv\Scripts\python.exe -m ruff format --check backend/` -> 185 files checked, all formatted.
7. Static type checking:
   `backend\.venv\Scripts\python.exe -m mypy --config-file backend/mypy.ini backend/app/optimizer/semantic_cache.py backend/app/services/ai_gateway.py` -> Success: no issues found in 2 source files.
8. Static application security testing (SAST):
   `backend\.venv\Scripts\python.exe -m bandit -c backend/pyproject.toml -r backend/app/optimizer/semantic_cache.py backend/app/services/ai_gateway.py` -> 0 issues identified across 1179 LOC.

ACTUAL RESULTS:
- 100% pass rate on all regression tests and full backend test suite (340/340 tests passed).
- Zero linting, formatting, typing, or security defects.
- Exact response-cache cross-model and cross-context collision completely resolved.

ACCEPTANCE CRITERIA STATUS:
- Cache collision regression tests pass: SATISFIED (29/29 passed in `test_cache_identity.py`).
- Existing cache tests pass: SATISFIED (4/4 passed in `test_semantic_cache.py`).
- Relevant static checks pass: SATISFIED (Ruff, Mypy, Bandit all green).
- No security regression: SATISFIED (Strict tenant key isolation confirmed; Bandit SAST scan 0 issues).
- Final diff remains scoped to CACHE-01: SATISFIED (Scoped strictly to `semantic_cache.py`, `ai_gateway.py`, and `test_cache_identity.py`).

SECURITY VERIFICATION:
- Tenant isolation is strictly preserved via `tenant_id` prefix in Redis keys (`cache:exact:{tenant_id}:{exact_key}`) and memory vector stores.
- `test_different_tenant_different_identity` and `test_gateway_exact_cache_isolation_across_dimensions` explicitly verify that requests under different tenant IDs never share cache identity or reuse cached responses.
- Bandit SAST scan ran with 0 issues identified.

CI VERIFICATION:
- Full CI test parity verified locally: unit tests, contract tests, AI evaluation portfolio benchmark (8/8 passed, 48.74% net token reduction), and token optimization empirical benchmark (100/100 passed, 63.51% net token reduction).

REMAINING ISSUES:
- None within REPAIR-00 scope.

RISKS:
- In-flight or stored cache keys generated under v1.0 schema will experience an intentional one-time cache miss upon v2.0 deployment, preventing legacy contaminated entries from being served.

INFORMATION REQUIRED BY THE NEXT TASK:
- For REPAIR-01 (PROV-02 — Structured Conversation Contract): `GatewayInferenceProxy` passes `messages_as_dicts = [{"role": m.role, "content": m.content} for m in request.messages]` to `cache_mgr.get/set`. The cache helper `_canonical_messages_repr` in `semantic_cache.py` consumes structured dictionaries with `role` and `content`. As PROV-02 introduces canonical conversation contracts across provider adapters, the representation is already aligned.