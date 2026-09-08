# REPAIR-03 — DUP-02 CANONICAL PROVIDER RESOLUTION

Finding:
DUP-02

Objective:
Establish one authoritative model-to-provider resolution path.

Current defect:
Gateway contains independent substring-based provider routing.

Required invariant:

Every supported model resolves through one authoritative provider registry/resolution mechanism.

Required mappings must remain correct for:
- OpenAI
- Anthropic
- Gemini
- Groq
- DeepSeek
- OpenRouter

Required work:

1. Locate all provider-resolution implementations.
2. Select the authoritative implementation.
3. Migrate gateway callers.
4. Remove active duplicate heuristics.
5. Add regression tests.

Tests:
deepseek
groq
gpt
claude
gemini
openrouter

Forbidden:
Do not change provider adapter internals unless required.
Do not redesign routing strategy.

Definition of done:
No active request path contains an independent provider-resolution rule.

==================================================
ACTUAL EXECUTION RESULT
==================================================

STATUS:
COMPLETED

ROOT CAUSE:
1. Independent Substring Heuristics in AI Gateway: In `backend/app/services/ai_gateway.py` (`chat_completions` and `chat_completions_stream`), model-to-provider resolution for Tier 1 Exact Match Cache keys and tenant BYOK credential lookup historically used a hardcoded inline ternary expression:
   `provider = "gemini" if "gemini" in request.model.lower() else ("openai" if "gpt" in request.model.lower() else ("anthropic" if "claude" in request.model.lower() else "openrouter"))`
   This duplicate heuristic failed to recognize Groq (`llama-...`), DeepSeek (`deepseek-...`), and OpenAI reasoning models (`o1`, `o3`), incorrectly classifying them as `"openrouter"`. Consequently, cache lookups and BYOK key lookups used the wrong provider namespace relative to the downstream provider adapter.
2. Upstream Dispatcher Duplicate Substring Evaluation: In `backend/app/core/llm_provider.py` (`call_upstream_llm_detailed`), an independent boolean chain (`is_anthropic`, `is_openai`, `is_groq`, `is_deepseek`, `is_openrouter`, `is_gemini`) was computed before routing to retrieve BYOK keys. This duplicated the `ModelRouter` resolution logic and failed to align with slash-form model identifiers (e.g. `meta-llama/llama-3.1-70b` under OpenRouter).

INVARIANT:
1. Single Authoritative Resolution Path: Every model-to-provider resolution on an active request path must originate from the authoritative `ProviderRegistry.resolve_provider_name_for_model(model)` in `backend/app/providers/registry.py`, which is the exact mechanism consumed by `ModelRouter` and failover dispatch.
2. Cross-Subsystem Resolution Identity: For any given model:
   - AI Gateway Exact Cache key `provider` parameter,
   - AI Gateway BYOK decrypted key lookup,
   - Upstream dispatcher BYOK credential injection,
   - Upstream dispatcher platform fallback key selection, and
   - Downstream `ModelRouter` adapter execution
   resolve to the identical canonical provider name (`openai`, `anthropic`, `gemini`, `groq`, `deepseek`, or `openrouter`).
3. Zero Magic Substring Heuristics on Request Paths: No active execution or caching path may contain independent substring or ternary routing rules.

CHANGES:
1. AI Gateway Migration (`backend/app/services/ai_gateway.py`):
   - In `GatewayInferenceProxy.chat_completions`: replaced the inline ternary substring heuristic with `get_provider_registry().resolve_provider_name_for_model(request.model)` for exact cache lookup, cache insertion, and BYOK credential lookup.
   - In `GatewayInferenceProxy.chat_completions_stream`: replaced the inline ternary substring heuristic with `get_provider_registry().resolve_provider_name_for_model(request.model)` for streaming exact cache lookup and insertion.
2. Upstream LLM Dispatcher Migration (`backend/app/core/llm_provider.py`):
   - Reordered execution in `call_upstream_llm_detailed` so `router.route(routing_policy)` executes first.
   - Removed the duplicate `is_anthropic`, `is_openai`, `is_groq`, `is_deepseek`, `is_openrouter`, `is_gemini` substring heuristic chain.
   - Mapped `decision.selected_provider` to provider settings keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`) and retrieved BYOK decrypted key for `decision.selected_provider`, ensuring credentials always align with the authoritatively selected provider adapter.
3. Unit & Regression Test Suite (`backend/tests/unit/test_canonical_provider_resolution.py`):
   - Created comprehensive test suite with 99 tests covering all six canonical providers (`openai`, `anthropic`, `gemini`, `groq`, `deepseek`, `openrouter`) across 14 model families.
   - Verified direct authoritative registry resolution and fallback to Gemini.
   - Verified Gateway non-streaming exact cache identity and BYOK credential injection use canonical provider.
   - Verified Gateway streaming exact cache identity uses canonical provider.
   - Verified Upstream Dispatcher BYOK credential selection matches `decision.selected_provider`.

MODIFIED FILES:
- `backend/app/services/ai_gateway.py`
- `backend/app/core/llm_provider.py`
- `backend/tests/unit/test_canonical_provider_resolution.py`
- `docs/repair/R/REPAIR-03 — DUP-02 Canonical Provider Resolution.md`

TESTS ADDED OR CHANGED:
- `backend/tests/unit/test_canonical_provider_resolution.py` (99 tests):
  1. `TestAuthoritativeRegistryResolution.test_registry_resolves_required_providers` (14 parametrized tests): Pinning canonical mappings for `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini`, `claude-3-5-sonnet`, `claude-3-haiku`, `gemini-1.5-flash`, `gemini-1.5-pro`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `deepseek-chat`, `deepseek-reasoner`, `openrouter/auto`, and `meta-llama/llama-3.1-70b`.
  2. `TestAuthoritativeRegistryResolution.test_registry_default_fallback_is_gemini` (1 test): Verifying uncataloged models default to Gemini.
  3. `TestGatewayChatCompletionsCanonicalResolution.test_cache_identity_uses_authoritative_provider` (14 parametrized tests): Verifying exact cache `get` and `set` calls use canonical provider.
  4. `TestGatewayChatCompletionsCanonicalResolution.test_byok_injection_targets_authoritative_provider` (14 parametrized tests): Verifying BYOK manager lookup uses canonical provider.
  5. `TestGatewayChatCompletionsCanonicalResolution.test_gateway_resolution_matches_authoritative_resolver` (14 parametrized tests): Verifying Gateway-resolved provider strictly equals `resolve_provider_name_for_model`.
  6. `TestGatewayStreamCanonicalResolution.test_stream_cache_identity_uses_authoritative_provider` (14 parametrized tests): Verifying streaming exact cache `get` and `set` calls use canonical provider.
  7. `TestGatewayStreamCanonicalResolution.test_stream_resolution_matches_authoritative_resolver` (14 parametrized tests): Verifying streaming path matches authoritative resolver.
  8. `TestDispatcherByokSelection.test_byok_key_matches_routing_decision_provider` (14 parametrized tests): Verifying `call_upstream_llm_detailed` passes the selected provider's credentials to the failover manager.

TESTS AND CHECKS ACTUALLY EXECUTED:
1. Focused Canonical Provider Resolution Suite:
   - Command: `python -m pytest tests/unit/test_canonical_provider_resolution.py -v`
   - Result: 99 passed in 44.91s.
2. Gateway and Provider Foundation Integration Suite:
   - Command: `python -m pytest tests/test_gateway.py tests/test_provider_foundation.py -v`
   - Result: 41 passed in 4.23s.
3. Regression Suite for REPAIR-01 and REPAIR-02:
   - Command: `python -m pytest tests/unit/test_structured_conversation_contract.py tests/unit/test_canonical_token_accounting.py -v`
   - Result: 44 passed in 3.73s.
4. Cache, BYOK, and Provider Prompt Caching Suite:
   - Command: `python -m pytest tests/unit/test_cache_identity.py tests/test_byok.py tests/test_openai_compatibility.py tests/test_provider_prompt_caching.py -v`
   - Result: 60 passed in 14.58s.
5. Code Quality (Linter & Formatter):
   - Command: `ruff check app/ tests/unit/test_canonical_provider_resolution.py` -> All checks passed!
   - Command: `ruff format --check app/ tests/unit/test_canonical_provider_resolution.py` -> 142 files already formatted.
6. Type Checking:
   - Command: `mypy app/services/ai_gateway.py app/core/llm_provider.py app/providers/registry.py app/routing/router.py` -> Success: no issues found in 4 source files.
7. Security Scan:
   - Command: `bandit -r app/core/llm_provider.py app/services/ai_gateway.py app/providers/registry.py` -> 0 issues identified.
8. OpenAPI Contract Compatibility:
   - Command: `python scripts/check_openapi_breaking_changes.py` -> Zero breaking changes detected. Status: 100% Backward Compatible.

CI VERIFICATION:
- Implementation CI Run ID: `34288884322` (Commit: `d6c3b6f8050282aafa3743cad1375621d34701d3`, Status: `completed`, Conclusion: `success`)
- Documentation Verification CI Run ID: `34289571945` (Commit: `cdee98c`, Status: `completed`, Conclusion: `success`)
- Branch: `feat/repair-03-canonical-provider-resolution`
- Pull Request: #25 (`https://github.com/NguyenQuan121321/JakeAI/pull/25`)
- Overall Status: `completed`
- Overall Conclusion: `success`
- Job Breakdown (9 of 9 passed across Python 3.11 and 3.12):
  1. `Infrastructure & Workflow Linting`: completed - success
  2. `Code Quality & Type Analysis (3.12)`: completed - success
  3. `DevSecOps - Vulnerability Audit, SAST & License Compliance`: completed - success
  4. `Code Quality & Type Analysis (3.11)`: completed - success
  5. `DevSecOps - Secret & Key Leak Detection`: completed - success
  6. `Frontend Widget Build & Quality Verification`: completed - success
  7. `Automated Tests & AI RAG Regression (3.11)`: completed - success
  8. `Automated Tests & AI RAG Regression (3.12)`: completed - success
  9. `Container Packaging & Vulnerability Scan`: completed - success

ACCEPTANCE CRITERIA STATUS:
- [x] All provider-resolution implementations located.
- [x] Authoritative implementation selected (`ProviderRegistry.resolve_provider_name_for_model`).
- [x] Gateway callers migrated in both non-streaming (`chat_completions`) and streaming (`chat_completions_stream`) paths.
- [x] Duplicate substring heuristics removed from `ai_gateway.py` and `llm_provider.py`.
- [x] Required mappings verified for OpenAI, Anthropic, Gemini, Groq, DeepSeek, and OpenRouter.
- [x] Provider adapter internals preserved without unnecessary modifications.
- [x] Routing strategy preserved without redesign.
- [x] 99 regression tests added and passing.
- [x] No active request path contains an independent provider-resolution rule.
- [x] CI green with all 9 jobs passing on PR #25.

SECURITY & TENANT ISOLATION:
- Tenant isolation is strictly preserved: BYOK decrypted keys are requested strictly within the caller's `tenant_id` namespace using the authoritatively selected provider name.
- Upstream credentials remain transient and are never leaked into cache keys, logs, or metrics records.

REMAINING ISSUES:
- None for REPAIR-03.

RISKS:
- Models not cataloged in `ModelCapabilityCatalog` default to `gemini` under `resolve_provider_name_for_model`, which is consistent with existing system defaults. If future providers are added, their prefix/naming rules must be registered directly in `ProviderRegistry.resolve_provider_name_for_model`.

NEXT TASK:
- REPAIR-04 — PROV-01 Shared HTTP Lifecycle