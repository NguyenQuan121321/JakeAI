# JakeAI — Static Code Analysis: Provider Architecture & BYOK Audit

**Audit Date:** September 2026  
**Status:** Audit Completed  
**Domain:** Provider Abstraction, Adapter Boundaries, HTTP Transport, and BYOK Platform Hardening  

---

## 1. Architectural Baseline

The JakeAI Provider Foundation was designed to provide vendor-agnostic routing, tenant-isolated BYOK key injection, bounded failover, and fine-grained provider prompt cache telemetry across six upstream providers:
- **Anthropic** (`claude-3-5-sonnet`, `claude-3-haiku`, `claude-3-opus`)
- **OpenAI** (`gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini`)
- **Gemini** (`gemini-1.5-flash`, `gemini-1.5-pro`)
- **Groq** (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`)
- **DeepSeek** (`deepseek-chat`)
- **OpenRouter** (unified meta-provider)

The foundation is built on an explicit `LLMProvider` Protocol (`app/providers/base.py`) requiring:
```python
class LLMProvider(Protocol):
    async def complete(self, request: ProviderRequest, client: httpx.AsyncClient | None = None) -> ProviderResponse: ...
    async def stream(self, request: ProviderRequest, client: httpx.AsyncClient | None = None) -> AsyncIterator[StreamChunk]: ...
    def capabilities(self, model: str) -> ModelCapabilities: ...
```

---

## 2. Provider Abstraction Findings

### Finding PROV-01: Per-Request HTTP Client Creation in Dispatch Hot Path
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/core/llm_provider.py` (Lines 142–147)
- **Current Behavior:**  
  ```python
  async with httpx.AsyncClient(timeout=timeout) as client:
      resp = await failover_mgr.execute_with_failover(
          request=provider_req,
          decision=decision,
          client=client,
      )
  ```
- **Problem:**  
  A new `httpx.AsyncClient` is instantiated and torn down on **every single upstream inference call**.
- **Evidence:**  
  `call_upstream_llm_detailed` creates the context manager on each request. The underlying connection pool, DNS cache, and TLS session cache are destroyed immediately upon response completion.
- **Impact:**  
  1. Latency penalty: Every upstream call pays a full TLS handshake penalty (50–150ms depending on provider geographical distance).
  2. Socket exhaustion: Under concurrent workloads (e.g. 100 requests/sec), ephemeral port exhaustion (`TIME_WAIT` socket buildup) occurs on the host operating system.
- **Recommended Solution:**  
  Manage a shared, persistent `httpx.AsyncClient` singleton bound to the application lifespan in `app/main.py`:
  ```python
  # app/core/http_client.py
  _client: httpx.AsyncClient | None = None

  def get_http_client() -> httpx.AsyncClient: ...
  async def close_http_client() -> None: ...
  ```
- **Alternative:** Pass a shared client from FastAPI request state or use `httpx.AsyncClient` pool with connection limits (`max_connections=100`, `max_keepalive_connections=20`).
- **Complexity:** Low.
- **Risk:** Low (requires ensuring proper shutdown in FastAPI `lifespan`).
- **Expected Benefit:** 50–120ms latency reduction on all cache-miss inference calls; zero risk of TCP port exhaustion.
- **Measurement Method:** Benchmark TTFB (time to first byte) with `httpx` connection reuse vs unpooled clients under 50 concurrent requests.

---

### Finding PROV-02: Structured Conversation History Truncated in `ProviderRequest`
- **Severity:** `CRITICAL`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/providers/base.py` (Line 137), `backend/app/services/ai_gateway.py` (Line 284, 380)
- **Current Behavior:**  
  1. `ProviderRequest` defines input as:
     ```python
     prompt: str
     system_instruction: str | None = None
     ```
     It completely lacks a `messages: list[dict[str, Any]]` or `messages: list[ChatMessage]` field!
  2. In `ai_gateway.py:284`, the gateway extracts only the last user message:
     ```python
     last_user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
     ```
  3. In `OpenAIAdapter._prepare_payload` (`openai.py:96-102`), the adapter constructs:
     ```python
     messages = []
     if static_sys:
         messages.append({"role": "system", "content": static_sys.strip()})
     messages.append({"role": "user", "content": compiled.dynamic_suffix or request.prompt})
     ```
- **Problem:**  
  When an OpenAI-compatible multi-turn chat completion request arrives with multiple prior turns (`user`, `assistant`, `tool`), the prior conversation history is either flattened into a single text block (`compiled.dynamic_suffix`) or completely dropped if `effective_query` is overridden by optimization. The upstream provider never receives native OpenAI chat message objects (`role: assistant`, `role: user`).
- **Impact:**  
  Severe degradation of multi-turn conversation intelligence: models cannot distinguish their own prior responses from user turns, losing conversational context and persona coherence.
- **Recommended Solution:**  
  Add `messages: list[ChatMessage] | None = None` directly to `ProviderRequest`. When provided, adapters must translate and forward the structured messages directly into the provider's native format.
- **Alternative:** Format history using standard prompt serialization only for text-completion models.
- **Complexity:** Medium (requires updating all 6 provider adapters to forward `messages`).
- **Risk:** Medium (requires careful handling of two-zone prefix alignment with message lists).
- **Expected Benefit:** True OpenAI-compatible multi-turn chat behavior without context loss.
- **Measurement Method:** Multi-turn conversation benchmark verifying that assistant recall across 5 turns remains 100%.

---

### Finding PROV-03: Provider Substring Resolution Leaks and Omissions
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/services/ai_gateway.py` (Lines 342–350)
- **Current Behavior:**  
  ```python
  provider = (
      "gemini" if "gemini" in request.model.lower()
      else ("openai" if "gpt" in request.model.lower()
      else ("anthropic" if "claude" in request.model.lower() else "openrouter"))
  )
  ```
- **Problem:**  
  The AI Gateway's provider resolution logic is hardcoded and out of sync with the Provider Registry. It does not contain checks for `groq` or `deepseek`.
- **Evidence:**  
  If a user sends a request for `model="deepseek-chat"` to `/v1/chat/completions`:
  1. `ai_gateway.py` evaluates the ternary: `"gemini"` -> False, `"gpt"` -> False, `"claude"` -> False.
  2. It resolves `provider = "openrouter"`.
  3. It calls `byok_mgr.get_decrypted_key(tenant_id, "openrouter")` instead of checking for a `deepseek` key!
  4. If the tenant only configured a DeepSeek BYOK key, the gateway fails to inject it and falls back to platform credentials or errors.
- **Impact:** Complete failure of BYOK key injection for DeepSeek and Groq models in the AI Gateway.
- **Recommended Solution:**  
  Delete the ternary logic in `ai_gateway.py` and invoke `get_provider_registry().resolve_provider_name_for_model(request.model)`.
- **Complexity:** Low.
- **Risk:** Low.
- **Expected Benefit:** Instant support for all 6 providers in AI Gateway; fixes BYOK key resolution bug.

---

### Finding PROV-04: False Streaming in AI Gateway Proxy
- **Severity:** `HIGH`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/services/ai_gateway.py` (Lines 605–643)
- **Current Behavior:**  
  In `chat_completions_stream`:
  ```python
  # 1. Call model non-streaming (blocks until complete response arrives)
  output_text = await call_upstream_llm(prompt=last_user_msg, ...)
  
  # 2. Simulate streaming with word split and sleep
  words = output_text.split(" ")
  for i, word in enumerate(words):
      yield f"data: {json.dumps(chunk)}\n\n"
      await asyncio.sleep(0.002)
  ```
- **Problem:**  
  The gateway claims to provide SSE streaming, but it does **not** stream tokens from the upstream provider! Instead, it performs a blocking non-streaming request, waits for the entire generation to finish (e.g. 5–10 seconds), and then artificially "plays back" the response word-by-word with a 2ms sleep loop.
- **Evidence:**  
  Direct inspection of `ai_gateway.py:605-643`. Note that `app/providers/base.py` already defines `async def stream(...)` on every provider adapter, but `ai_gateway.py` completely bypasses it!
- **Impact:**  
  Time To First Token (TTFT) for streaming clients is identical to non-streaming calls (5–10x worse than real streaming). Users experience a frozen UI until generation finishes completely.
- **Recommended Solution:**  
  Call `adapter.stream(provider_req, client=client)` directly and yield SSE chunks as `StreamChunk` objects arrive from the upstream HTTP stream.
- **Complexity:** Medium.
- **Risk:** Low to Medium (requires accounting for tokens incrementally on stream disconnect).
- **Expected Benefit:** Dramatic TTFT improvement from ~4,000ms down to ~300–500ms for streaming clients.
- **Measurement Method:** Measure Time to First Token (TTFT) on a 500-token completion.

---

## 3. BYOK Platform Security Findings

### Finding BYOK-01: Insecure Key Derivation via Plain SHA-256 Concatenation
- **Severity:** `MEDIUM`
- **Confidence:** `HIGH`
- **File / Symbol / Location:** `backend/app/core/byok.py` (Lines 50–55)
- **Current Behavior:**  
  ```python
  def _derive_tenant_aesgcm(self, tenant_id: str) -> AESGCM:
      """Derive an isolated 32-byte AES-256-GCM key per tenant using HMAC-SHA256."""
      tenant_key = hashlib.sha256(
          self._master_secret + tenant_id.encode("utf-8")
      ).digest()
      return AESGCM(tenant_key)
  ```
- **Problem:**  
  1. The docstring explicitly claims to use `HMAC-SHA256`, but the code executes raw prefix concatenation: `hashlib.sha256(secret + message)`.
  2. While SHA-256 concatenation produces a 32-byte string, it does not provide the cryptographic guarantees of a formal Key Derivation Function (KDF) and deviates from standard cryptographic engineering practices.
- **Evidence:**  
  Python's `cryptography` library already provides RFC 5869 `HKDF` in `cryptography.hazmat.primitives.kdf.hkdf`.
- **Impact:** Architectural non-compliance with enterprise cryptographic standards (FIPS 140-3 / RFC 5869).
- **Recommended Solution:**  
  Replace concatenation with `HKDF`:
  ```python
  from cryptography.hazmat.primitives.kdf.hkdf import HKDF
  from cryptography.hazmat.primitives import hashes

  def _derive_tenant_aesgcm(self, tenant_id: str) -> AESGCM:
      hkdf = HKDF(
          algorithm=hashes.SHA256(),
          length=32,
          salt=None,
          info=f"jakeai-byok-tenant:{tenant_id}".encode(),
      )
      tenant_key = hkdf.derive(self._master_secret)
      return AESGCM(tenant_key)
  ```
  *(Note: Backward compatibility migration or re-encryption script required for existing stored ciphertexts).*
- **Complexity:** Low.
- **Risk:** High if executed without key migration; Low if performed as a versioned migration.
- **Expected Benefit:** True cryptographic tenant key isolation conforming to RFC 5869.

---

## 4. Provider Capability Architecture Review

The current `ModelCapabilities` schema in `app/providers/base.py` accurately models:
- Context limits
- JSON/tool capabilities
- Prompt cache support
- Reasoning flags (`supports_reasoning`)
- Pricing structures

### Recommendation:
Enforce that model routing decisions query `ModelCapabilityCatalog` exclusively, rather than performing regex/substring checks on model strings.
