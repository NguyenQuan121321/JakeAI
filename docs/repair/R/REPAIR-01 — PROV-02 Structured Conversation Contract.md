# REPAIR-01 — PROV-02 STRUCTURED CONVERSATION CONTRACT

Finding:
PROV-02

Priority:
CRITICAL

Objective:
Preserve complete multi-turn conversation semantics from gateway to provider adapters.

Current defect to verify:
ProviderRequest does not carry structured messages, while the gateway reduces conversation context to the last user message or flattened text.

Required invariant:

A structured conversation must preserve:

- role
- ordering
- content
- assistant turns
- tool messages
- tool call identity
- system instructions

through the provider boundary without semantic loss.

Required work:

1. Inspect GatewayChatRequest.
2. Inspect ProviderRequest.
3. Inspect all active provider adapters.
4. Identify every point where history is flattened or discarded.
5. Introduce/reuse canonical ChatMessage representation.
6. Extend provider request contract appropriately.
7. Map canonical messages into each provider format.
8. Preserve backward compatibility for valid single-prompt callers.
9. Add contract tests for multi-turn behavior.

Required tests:

- 5-turn conversation
- assistant recall
- system instruction preservation
- tool message preservation
- ordering preservation
- provider adapter translation

Forbidden:

Do not redesign cache identity unless strictly required by the message contract.
Do not repair unrelated token accounting.

Definition of done:

No valid multi-turn conversation loses semantic history at the provider boundary.

==================================================
ACTUAL EXECUTION RESULT
==================================================

STATUS:
COMPLETED

ROOT CAUSE:
`ProviderRequest` in `backend/app/providers/base.py` originally lacked structured conversation representation (defining only `prompt: str` and `system_instruction: str | None`), forcing inference entrypoints to either drop multi-turn context or flatten conversation history into a single string. Specifically:
1. `GatewayInferenceProxy.chat_completions` and `chat_completions_stream` in `backend/app/services/ai_gateway.py` extracted only the last user turn (`last_user_msg`) and passed it to `call_upstream_llm_detailed`, discarding earlier user, assistant, and tool turns.
2. `call_upstream_llm_detailed` and `call_upstream_llm` in `backend/app/core/llm_provider.py` did not accept a structured message collection and only constructed `ProviderRequest` with a scalar prompt.
3. `JakeAIBackend.generate` in `backend/app/agent/backends/jakeai.py` manually concatenated history turns into a single plain-text prompt string (`"User: ...\nAssistant: ..."`).
4. All 6 active provider adapters (`OpenAIAdapter`, `DeepSeekAdapter`, `GroqAdapter`, `OpenRouterAdapter`, `AnthropicAdapter`, `GeminiAdapter`) constructed single-turn payloads using `compiled.dynamic_suffix or request.prompt` and lacked support for structured message history, dropping assistant persona, prior tool calls, and alternating turn boundaries at the native API provider boundary.

INVARIANT:
A structured conversation must preserve:
- role (system, developer, user, assistant, tool)
- ordering
- content
- assistant turns
- tool messages
- tool call identity (call ID, function name, arguments)
- system instructions
through the provider boundary without semantic loss. Single-prompt callers remain backward-compatible without behavioral regression.

CHANGES:
1. Canonical ChatMessage & ProviderRequest Contract (`backend/app/providers/base.py`):
   - Defined canonical `ChatMessage` supporting `role`, `content`, `name`, `tool_call_id`, and `tool_calls`.
   - Extended `ProviderRequest` with optional `messages: list[ChatMessage] | None = None` and changed `prompt: str = Field(default="")`.
   - Implemented `@model_validator(mode="after")` to automatically synchronize `self.prompt` from the last user message and `self.system_instruction` from system turns when `messages` is provided, preserving backward compatibility for scalar prompt consumers.
2. Native Provider Formatters (`backend/app/providers/base.py`):
   - Implemented `format_openai_chat_messages`: maps canonical message list to OpenAI chat completions format, preserving assistant `tool_calls`, tool results with `tool_call_id`, and system prompts.
   - Implemented `format_anthropic_chat_messages`: extracts system instructions into top-level `system` text and maps non-system turns into Anthropic's alternating `user`/`assistant` schema with `tool_use` and `tool_result` content blocks.
   - Implemented `format_gemini_chat_contents`: extracts system instructions into `systemInstruction` and maps non-system turns into Gemini's `user`, `model` (with `functionCall`), and `function` (with `functionResponse`) turns.
3. Provider Adapter Implementation (`backend/app/providers/`):
   - Updated `OpenAIAdapter`, `DeepSeekAdapter`, `GroqAdapter`, and `OpenRouterAdapter` to construct native payloads via `format_openai_chat_messages`.
   - Updated `AnthropicAdapter` to construct native payloads via `format_anthropic_chat_messages`.
   - Updated `GeminiAdapter` to construct native payloads via `format_gemini_chat_contents`.
   - Exported `ChatMessage` and formatters in `backend/app/providers/__init__.py`.
4. Upstream Provider Dispatch Layer (`backend/app/core/llm_provider.py`):
   - Extended `call_upstream_llm_detailed` and `call_upstream_llm` to accept optional `messages: list[ChatMessage] | None = None` and `response_format` and pass them to `ProviderRequest`.
5. AI Gateway Integration (`backend/app/services/ai_gateway.py`):
   - Replaced duplicate `ChatMessage` with canonical import from `app.providers.base`.
   - Updated `GatewayInferenceProxy.chat_completions` and `chat_completions_stream` to forward full structured message history, tools, and response format to upstream inference without truncation or flattening.
6. Agent Backend Integration (`backend/app/agent/backends/jakeai.py`):
   - Converted `AgentMessage` objects to canonical `ChatMessage` objects and dispatched them directly through `call_upstream_llm_detailed` with structured history intact.

MODIFIED FILES:
- `backend/app/providers/base.py`
- `backend/app/providers/__init__.py`
- `backend/app/providers/openai.py`
- `backend/app/providers/deepseek.py`
- `backend/app/providers/groq.py`
- `backend/app/providers/openrouter.py`
- `backend/app/providers/anthropic.py`
- `backend/app/providers/gemini.py`
- `backend/app/core/llm_provider.py`
- `backend/app/services/ai_gateway.py`
- `backend/app/agent/backends/jakeai.py`
- `backend/tests/unit/test_structured_conversation_contract.py`
- `docs/repair/R/REPAIR-01 — PROV-02 Structured Conversation Contract.md`

TESTS ADDED OR CHANGED:
- `backend/tests/unit/test_structured_conversation_contract.py` (25 comprehensive test cases):
  - `TestProviderRequestContract`:
    - `test_provider_request_with_structured_messages`
    - `test_provider_request_backward_compatibility_single_prompt`
    - `test_provider_request_explicit_prompt_preserved`
    - `test_chat_message_dict_initialization`
  - `TestFiveTurnConversation`:
    - `test_5_turn_openai_adapter`
    - `test_5_turn_anthropic_adapter`
    - `test_5_turn_gemini_adapter`
    - `test_5_turn_deepseek_adapter`
    - `test_5_turn_groq_adapter`
    - `test_5_turn_openrouter_adapter`
  - `TestAssistantRecallPreservation`:
    - `test_assistant_recall_across_turns`
    - `test_anthropic_assistant_recall`
    - `test_gemini_assistant_recall`
  - `TestSystemInstructionPreservation`:
    - `test_system_message_in_messages_list_not_duplicated_openai`
    - `test_system_instruction_injected_when_not_in_messages_openai`
    - `test_system_instruction_extracted_anthropic`
    - `test_system_instruction_extracted_gemini`
  - `TestToolMessagePreservation`:
    - `test_tool_preservation_openai`
    - `test_tool_preservation_anthropic`
    - `test_tool_preservation_gemini`
  - `TestOrderingPreservation`:
    - `test_strict_order_preservation`
  - `TestSinglePromptBackwardCompatibility`:
    - `test_single_prompt_openai`
    - `test_single_prompt_anthropic`
    - `test_single_prompt_gemini`
  - `TestGatewayMultiTurnDispatch`:
    - `test_gateway_forwards_structured_messages_to_upstream`

TESTS AND CHECKS ACTUALLY EXECUTED:
1. Focused unit & regression tests:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_structured_conversation_contract.py -v` -> 25 passed in 2.05s.
2. Related subsystem tests:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_provider_foundation.py backend/tests/test_provider_prompt_caching.py backend/tests/test_commercial_services.py backend/tests/test_harmonization.py backend/tests/unit/test_cache_identity.py backend/tests/test_agent_platform.py -v` -> 92 passed in 15.69s.
3. Full repository test suite:
   `backend\.venv\Scripts\python.exe -m pytest backend/tests` -> 365 passed, 1 warning in 110.38s.
4. Static code analysis & linting:
   `backend\.venv\Scripts\python.exe -m ruff check backend/` -> All checks passed!
5. Code style & formatting:
   `backend\.venv\Scripts\python.exe -m ruff format --check backend/` -> 186 files checked, all formatted.
6. Static type checking:
   `backend\.venv\Scripts\python.exe -m mypy --config-file backend/mypy.ini backend/app/providers/ backend/app/services/ai_gateway.py backend/app/core/llm_provider.py backend/app/agent/backends/jakeai.py` -> Success: no issues found in 13 source files.
7. Static application security testing (SAST):
   `backend\.venv\Scripts\python.exe -m bandit -c backend/pyproject.toml -r backend/app/providers/ backend/app/services/ai_gateway.py backend/app/core/llm_provider.py backend/app/agent/backends/jakeai.py` -> No issues identified across 3777 LOC.

ACTUAL RESULTS:
- 100% pass rate on new contract tests (25/25) and full backend test suite (365/365).
- Zero linting, formatting, type checking, or security defects.
- Multi-turn conversation semantics, assistant turns, tool calls, tool results, and system instructions are fully preserved across the gateway, provider request boundary, and all 6 provider adapters.

ACCEPTANCE CRITERIA STATUS:
- 5-turn conversation preserved: SATISFIED (tested and verified across all 6 provider adapters).
- Assistant recall preserved: SATISFIED (prior assistant responses retained intact across multi-turn context).
- System instruction preservation: SATISFIED (system messages in messages or via parameter preserved without duplication).
- Tool message preservation: SATISFIED (tool calls and results preserved with call ID and function name).
- Ordering preservation: SATISFIED (strict turn order maintained through provider boundary).
- Provider adapter translation: SATISFIED (verified across OpenAI, Anthropic, Gemini, DeepSeek, Groq, OpenRouter).
- Backward compatibility for valid single-prompt callers: SATISFIED (verified across all 6 adapters).
- Final diff remains scoped to PROV-02: SATISFIED (no unrelated token accounting or cache redesign).

SECURITY VERIFICATION:
- BYOK tenant key resolution and credential isolation remain intact.
- Bandit SAST scan scanned 3777 lines of code with 0 issues identified.
- Tenant scoping and sensitive parameter protection preserved across all provider request contracts.

CI VERIFICATION:
- Full CI test parity verified locally: 365/365 tests passed, including Phase 00 CI/CD AI evaluation benchmark (8/8 workloads passed, 48.74% portfolio net reduction) and token optimization benchmark (100/100 requests evaluated, 63.51% net reduction).

REMAINING ISSUES:
- None within REPAIR-01 scope.

RISKS:
- None. Full backward compatibility maintained for existing single-prompt callers and legacy upstream call wrappers.

INFORMATION REQUIRED BY THE NEXT TASK:
- For REPAIR-02 (TOK-02 — Canonical Token Accounting): Provider adapters now receive complete multi-turn `request.messages`. Token accounting for multi-turn requests can directly consume the structured messages list rather than relying on pruned single-turn approximations.