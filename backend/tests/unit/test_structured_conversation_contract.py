"""Comprehensive Regression and Contract Tests for REPAIR-01 (PROV-02).

Validates structured conversation contract preservation from the AI Gateway
through the canonical ProviderRequest boundary to all 6 provider adapters:
- OpenAI
- Anthropic
- Gemini
- DeepSeek
- Groq
- OpenRouter
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from app.providers import (
    AnthropicAdapter,
    ChatMessage,
    DeepSeekAdapter,
    GeminiAdapter,
    GroqAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
    ProviderRequest,
    format_anthropic_chat_messages,
    format_gemini_chat_contents,
    format_openai_chat_messages,
)
from app.services.ai_gateway import (
    GatewayChatRequest,
    GatewayInferenceProxy,
    QuotaManager,
)

# ==============================================================================
# 1. ProviderRequest Contract & Initialization Tests
# ==============================================================================


class TestProviderRequestContract:
    """Validate ProviderRequest data contract and backward compatibility."""

    def test_provider_request_with_structured_messages(self) -> None:
        """ProviderRequest accepts structured messages and auto-populates prompt from last user turn."""
        msgs = [
            ChatMessage(role="system", content="You are a financial advisor."),
            ChatMessage(role="user", content="What is compounding interest?"),
            ChatMessage(
                role="assistant",
                content="Compounding interest is interest on interest.",
            ),
            ChatMessage(role="user", content="Give me a formula."),
        ]
        req = ProviderRequest(
            model="gpt-4o",
            messages=msgs,
        )
        assert req.messages == msgs
        assert req.prompt == "Give me a formula."
        assert req.system_instruction == "You are a financial advisor."

    def test_provider_request_backward_compatibility_single_prompt(self) -> None:
        """Single-prompt callers without messages remain fully functional."""
        req = ProviderRequest(
            model="claude-3-5-sonnet-20241022",
            prompt="Explain inflation.",
            system_instruction="Be concise.",
        )
        assert req.prompt == "Explain inflation."
        assert req.messages is None
        assert req.system_instruction == "Be concise."

    def test_provider_request_explicit_prompt_preserved(self) -> None:
        """When prompt is explicitly provided alongside messages, it is not overwritten."""
        msgs = [ChatMessage(role="user", content="Message content")]
        req = ProviderRequest(
            model="gemini-1.5-flash",
            prompt="Explicit override prompt",
            messages=msgs,
        )
        assert req.prompt == "Explicit override prompt"
        assert req.messages == msgs


# ==============================================================================
# 2. Five-Turn Conversation Preservation Across All 6 Providers
# ==============================================================================


class TestFiveTurnConversation:
    """Validate that 5-turn conversations preserve all turns across all 6 provider adapters."""

    @pytest.fixture
    def five_turn_messages(self) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content="You are a portfolio assistant."),
            ChatMessage(role="user", content="Turn 1: What is diversification?"),
            ChatMessage(
                role="assistant",
                content="Turn 2: Diversification spreads risk across assets.",
            ),
            ChatMessage(
                role="user", content="Turn 3: Can you give an example portfolio?"
            ),
            ChatMessage(
                role="assistant",
                content="Turn 4: 60% stocks, 30% bonds, 10% cash/commodities.",
            ),
            ChatMessage(role="user", content="Turn 5: What about tech stock weight?"),
        ]

    def test_openai_five_turn(self, five_turn_messages: list[ChatMessage]) -> None:
        req = ProviderRequest(model="gpt-4o", messages=five_turn_messages)
        adapter = OpenAIAdapter()
        _, payload = adapter._prepare_payload(req)
        messages = payload["messages"]
        assert len(messages) == 6  # 1 system + 5 user/assistant turns
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a portfolio assistant."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Turn 1: What is diversification?"
        assert messages[2]["role"] == "assistant"
        assert (
            messages[2]["content"]
            == "Turn 2: Diversification spreads risk across assets."
        )
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "Turn 3: Can you give an example portfolio?"
        assert messages[4]["role"] == "assistant"
        assert (
            messages[4]["content"]
            == "Turn 4: 60% stocks, 30% bonds, 10% cash/commodities."
        )
        assert messages[5]["role"] == "user"
        assert messages[5]["content"] == "Turn 5: What about tech stock weight?"

    def test_deepseek_five_turn(self, five_turn_messages: list[ChatMessage]) -> None:
        req = ProviderRequest(model="deepseek-chat", messages=five_turn_messages)
        adapter = DeepSeekAdapter()
        _, payload = adapter._prepare_payload(req)
        messages = payload["messages"]
        assert len(messages) == 6
        assert [m["role"] for m in messages] == [
            "system",
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
        ]
        assert "Turn 5" in messages[-1]["content"]

    def test_groq_five_turn(self, five_turn_messages: list[ChatMessage]) -> None:
        req = ProviderRequest(
            model="llama-3.3-70b-versatile", messages=five_turn_messages
        )
        adapter = GroqAdapter()
        _, payload = adapter._prepare_payload(req)
        messages = payload["messages"]
        assert len(messages) == 6
        assert [m["role"] for m in messages] == [
            "system",
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
        ]
        assert "Turn 5" in messages[-1]["content"]

    def test_openrouter_five_turn(self, five_turn_messages: list[ChatMessage]) -> None:
        req = ProviderRequest(
            model="anthropic/claude-3.5-sonnet", messages=five_turn_messages
        )
        adapter = OpenRouterAdapter()
        _, payload = adapter._prepare_payload(req)
        messages = payload["messages"]
        assert len(messages) == 6
        assert [m["role"] for m in messages] == [
            "system",
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
        ]
        assert "Turn 5" in messages[-1]["content"]

    def test_anthropic_five_turn(self, five_turn_messages: list[ChatMessage]) -> None:
        req = ProviderRequest(
            model="claude-3-5-sonnet-20241022", messages=five_turn_messages
        )
        adapter = AnthropicAdapter()
        _, payload = adapter._prepare_payload(req)
        assert len(payload["system"]) >= 1
        assert "You are a portfolio assistant." in payload["system"][0]["text"]
        messages = payload["messages"]
        assert len(messages) == 5  # Non-system turns
        assert [m["role"] for m in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
        ]
        assert messages[0]["content"] == "Turn 1: What is diversification?"
        assert (
            messages[1]["content"]
            == "Turn 2: Diversification spreads risk across assets."
        )
        assert messages[2]["content"] == "Turn 3: Can you give an example portfolio?"
        assert (
            messages[3]["content"]
            == "Turn 4: 60% stocks, 30% bonds, 10% cash/commodities."
        )
        assert messages[4]["content"] == "Turn 5: What about tech stock weight?"

    def test_gemini_five_turn(self, five_turn_messages: list[ChatMessage]) -> None:
        req = ProviderRequest(model="gemini-1.5-flash", messages=five_turn_messages)
        adapter = GeminiAdapter()
        _, payload = adapter._prepare_payload(req)
        sys_inst = payload.get("systemInstruction", {})
        assert sys_inst["parts"][0]["text"] == "You are a portfolio assistant."
        contents = payload["contents"]
        assert len(contents) == 5  # Non-system turns
        assert [c["role"] for c in contents] == [
            "user",
            "model",
            "user",
            "model",
            "user",
        ]
        assert contents[0]["parts"][0]["text"] == "Turn 1: What is diversification?"
        assert (
            contents[1]["parts"][0]["text"]
            == "Turn 2: Diversification spreads risk across assets."
        )
        assert (
            contents[2]["parts"][0]["text"]
            == "Turn 3: Can you give an example portfolio?"
        )
        assert (
            contents[3]["parts"][0]["text"]
            == "Turn 4: 60% stocks, 30% bonds, 10% cash/commodities."
        )
        assert (
            contents[4]["parts"][0]["text"] == "Turn 5: What about tech stock weight?"
        )


# ==============================================================================
# 3. Assistant Recall Preservation Tests
# ==============================================================================


class TestAssistantRecallPreservation:
    """Validate that assistant prior responses are faithfully preserved across adapters."""

    def test_assistant_recall_openai(self) -> None:
        msgs = [
            ChatMessage(role="user", content="My favorite ticker is AAPL."),
            ChatMessage(
                role="assistant", content="I will remember that your favorite is AAPL."
            ),
            ChatMessage(role="user", content="What was my favorite ticker?"),
        ]
        req = ProviderRequest(model="gpt-4o", messages=msgs)
        adapter = OpenAIAdapter()
        _, payload = adapter._prepare_payload(req)
        assert any(
            m["role"] == "assistant" and "favorite is AAPL" in str(m.get("content", ""))
            for m in payload["messages"]
        )

    def test_assistant_recall_anthropic(self) -> None:
        msgs = [
            ChatMessage(role="user", content="My favorite ticker is AAPL."),
            ChatMessage(
                role="assistant", content="I will remember that your favorite is AAPL."
            ),
            ChatMessage(role="user", content="What was my favorite ticker?"),
        ]
        req = ProviderRequest(model="claude-3-5-sonnet", messages=msgs)
        adapter = AnthropicAdapter()
        _, payload = adapter._prepare_payload(req)
        assert any(
            m["role"] == "assistant" and "favorite is AAPL" in str(m.get("content", ""))
            for m in payload["messages"]
        )

    def test_assistant_recall_gemini(self) -> None:
        msgs = [
            ChatMessage(role="user", content="My favorite ticker is AAPL."),
            ChatMessage(
                role="assistant", content="I will remember that your favorite is AAPL."
            ),
            ChatMessage(role="user", content="What was my favorite ticker?"),
        ]
        req = ProviderRequest(model="gemini-1.5-pro", messages=msgs)
        adapter = GeminiAdapter()
        _, payload = adapter._prepare_payload(req)
        assert any(
            c["role"] == "model"
            and any("favorite is AAPL" in p.get("text", "") for p in c.get("parts", []))
            for c in payload["contents"]
        )


# ==============================================================================
# 4. System Instruction Preservation Tests
# ==============================================================================


class TestSystemInstructionPreservation:
    """Validate system instructions preservation via message history and top-level field."""

    def test_system_instruction_via_message(self) -> None:
        msgs = [
            ChatMessage(
                role="system", content="Strict policy: Output exclusively JSON."
            ),
            ChatMessage(role="user", content="Give me 3 stocks."),
        ]
        req = ProviderRequest(model="gpt-4o", messages=msgs)
        assert req.system_instruction == "Strict policy: Output exclusively JSON."
        adapter = OpenAIAdapter()
        _, payload = adapter._prepare_payload(req)
        assert payload["messages"][0]["role"] == "system"
        assert (
            payload["messages"][0]["content"]
            == "Strict policy: Output exclusively JSON."
        )

    def test_system_instruction_via_top_level_field(self) -> None:
        msgs = [ChatMessage(role="user", content="Give me 3 stocks.")]
        req = ProviderRequest(
            model="gpt-4o",
            system_instruction="Strict policy: Output exclusively JSON.",
            messages=msgs,
        )
        adapter = OpenAIAdapter()
        _, payload = adapter._prepare_payload(req)
        assert payload["messages"][0]["role"] == "system"
        assert (
            payload["messages"][0]["content"]
            == "Strict policy: Output exclusively JSON."
        )

    def test_system_instruction_anthropic_ephemeral_cache(self) -> None:
        msgs = [
            ChatMessage(
                role="system", content="word " * 2000
            ),  # Large enough for cache eligibility (2000 tokens >= 1024)
            ChatMessage(role="user", content="Hello"),
        ]
        req = ProviderRequest(model="claude-3-5-sonnet-20241022", messages=msgs)
        adapter = AnthropicAdapter()
        _, payload = adapter._prepare_payload(req)
        assert len(payload["system"]) >= 1
        assert "cache_control" in payload["system"][0]
        assert payload["system"][0]["cache_control"]["type"] == "ephemeral"


# ==============================================================================
# 5. Tool Message & Tool Call Identity Preservation Tests
# ==============================================================================


class TestToolMessagePreservation:
    """Validate that assistant tool_calls and tool messages preserve IDs and arguments."""

    @pytest.fixture
    def tool_conversation(self) -> list[ChatMessage]:
        return [
            ChatMessage(role="user", content="What is the price of NVDA?"),
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "call_nvda_123",
                        "type": "function",
                        "function": {
                            "name": "get_stock_price",
                            "arguments": json.dumps({"ticker": "NVDA"}),
                        },
                    }
                ],
            ),
            ChatMessage(
                role="tool",
                name="get_stock_price",
                tool_call_id="call_nvda_123",
                content=json.dumps({"ticker": "NVDA", "price": 125.50}),
            ),
            ChatMessage(role="user", content="What about its 52-week high?"),
        ]

    def test_tool_preservation_openai(
        self, tool_conversation: list[ChatMessage]
    ) -> None:
        req = ProviderRequest(model="gpt-4o", messages=tool_conversation)
        adapter = OpenAIAdapter()
        _, payload = adapter._prepare_payload(req)
        msgs = payload["messages"]

        # Turn 1: user
        assert msgs[1]["role"] == "user"
        # Turn 2: assistant with tool_calls
        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["tool_calls"][0]["id"] == "call_nvda_123"
        assert msgs[2]["tool_calls"][0]["function"]["name"] == "get_stock_price"
        # Turn 3: tool result
        assert msgs[3]["role"] == "tool"
        assert msgs[3]["tool_call_id"] == "call_nvda_123"
        assert "125.5" in msgs[3]["content"]
        # Turn 4: user
        assert msgs[4]["role"] == "user"

    def test_tool_preservation_anthropic(
        self, tool_conversation: list[ChatMessage]
    ) -> None:
        req = ProviderRequest(
            model="claude-3-5-sonnet-20241022", messages=tool_conversation
        )
        adapter = AnthropicAdapter()
        _, payload = adapter._prepare_payload(req)
        msgs = payload["messages"]

        # Assistant turn should contain tool_use block
        asst_msg = next(m for m in msgs if m["role"] == "assistant")
        tool_use_block = asst_msg["content"][0]
        assert tool_use_block["type"] == "tool_use"
        assert tool_use_block["id"] == "call_nvda_123"
        assert tool_use_block["name"] == "get_stock_price"
        assert tool_use_block["input"] == {"ticker": "NVDA"}

        # Tool result should be placed in user message as tool_result block
        tool_res_msg = msgs[2]
        assert tool_res_msg["role"] == "user"
        tool_res_block = tool_res_msg["content"][0]
        assert tool_res_block["type"] == "tool_result"
        assert tool_res_block["tool_use_id"] == "call_nvda_123"
        assert "125.5" in tool_res_block["content"]

    def test_tool_preservation_gemini(
        self, tool_conversation: list[ChatMessage]
    ) -> None:
        req = ProviderRequest(model="gemini-1.5-flash", messages=tool_conversation)
        adapter = GeminiAdapter()
        _, payload = adapter._prepare_payload(req)
        contents = payload["contents"]

        # Assistant turn mapped to 'model' with functionCall
        model_turn = next(c for c in contents if c["role"] == "model")
        fn_call = model_turn["parts"][0]["functionCall"]
        assert fn_call["name"] == "get_stock_price"
        assert fn_call["args"] == {"ticker": "NVDA"}

        # Tool turn mapped to 'function' with functionResponse
        fn_turn = next(c for c in contents if c["role"] == "function")
        fn_res = fn_turn["parts"][0]["functionResponse"]
        assert fn_res["name"] == "get_stock_price"
        assert "125.5" in fn_res["response"]["result"]


# ==============================================================================
# 6. Ordering Preservation Tests
# ==============================================================================


class TestOrderingPreservation:
    """Validate that message order is strictly preserved without reordering."""

    def test_ordering_openai(self) -> None:
        roles_sequence = ["user", "assistant", "user", "assistant", "user"]
        msgs = [
            ChatMessage(role=r, content=f"turn_{i}")
            for i, r in enumerate(roles_sequence)
        ]
        req = ProviderRequest(model="gpt-4o", messages=msgs)
        adapter = OpenAIAdapter()
        _, payload = adapter._prepare_payload(req)
        # Skip leading default system message if present
        non_sys = [m for m in payload["messages"] if m["role"] != "system"]
        assert [m["role"] for m in non_sys] == roles_sequence
        assert [m["content"] for m in non_sys] == [
            f"turn_{i}" for i in range(len(roles_sequence))
        ]

    def test_ordering_gemini(self) -> None:
        roles_in = ["user", "assistant", "user", "assistant", "user"]
        gemini_expected = ["user", "model", "user", "model", "user"]
        msgs = [
            ChatMessage(role=r, content=f"turn_{i}") for i, r in enumerate(roles_in)
        ]
        req = ProviderRequest(model="gemini-1.5-flash", messages=msgs)
        adapter = GeminiAdapter()
        _, payload = adapter._prepare_payload(req)
        contents = payload["contents"]
        assert [c["role"] for c in contents] == gemini_expected
        for i, c in enumerate(contents):
            assert c["parts"][0]["text"] == f"turn_{i}"


# ==============================================================================
# 7. Single Prompt Backward Compatibility Tests
# ==============================================================================


class TestSinglePromptBackwardCompatibility:
    """Validate that existing single-prompt callers without messages function identically."""

    def test_openai_single_prompt(self) -> None:
        req = ProviderRequest(
            model="gpt-4o-mini",
            prompt="Simple query",
            system_instruction="Be succinct.",
        )
        adapter = OpenAIAdapter()
        _, payload = adapter._prepare_payload(req)
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "Be succinct."
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "Simple query"

    def test_anthropic_single_prompt(self) -> None:
        req = ProviderRequest(
            model="claude-3-5-sonnet-20241022",
            prompt="Simple query",
            system_instruction="Be succinct.",
        )
        adapter = AnthropicAdapter()
        _, payload = adapter._prepare_payload(req)
        assert payload["system"][0]["text"] == "Be succinct."
        assert payload["messages"] == [{"role": "user", "content": "Simple query"}]

    def test_gemini_single_prompt(self) -> None:
        req = ProviderRequest(
            model="gemini-1.5-flash",
            prompt="Simple query",
            system_instruction="Be succinct.",
        )
        adapter = GeminiAdapter()
        _, payload = adapter._prepare_payload(req)
        assert payload["systemInstruction"]["parts"][0]["text"] == "Be succinct."
        assert payload["contents"] == [{"parts": [{"text": "Simple query"}]}]


# ==============================================================================
# 8. Gateway Multi-Turn Dispatch Tests
# ==============================================================================


class TestGatewayMultiTurnDispatch:
    """Validate that GatewayInferenceProxy correctly receives and forwards multi-turn messages."""

    @pytest.mark.asyncio
    async def test_gateway_dispatches_full_messages(self) -> None:
        msgs = [
            ChatMessage(role="system", content="System instruction"),
            ChatMessage(role="user", content="Turn 1"),
            ChatMessage(role="assistant", content="Reply 1"),
            ChatMessage(role="user", content="Turn 2"),
        ]
        request = GatewayChatRequest(
            model="gemini-1.5-flash",
            messages=msgs,
        )
        proxy = GatewayInferenceProxy(quota_manager=QuotaManager())

        captured_kwargs: dict[str, Any] = {}

        async def fake_call_upstream(**kwargs: Any) -> Any:
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            from app.providers.base import ProviderCacheTelemetry, UpstreamLLMResponse

            return UpstreamLLMResponse(
                text="Gateway final reply",
                model="gemini-1.5-flash",
                provider="gemini",
                telemetry=ProviderCacheTelemetry(
                    is_cache_eligible=False,
                    cache_hit=False,
                    cached_tokens=0,
                    uncached_input_tokens=100,
                    output_tokens=20,
                    provider="gemini",
                    model="gemini-1.5-flash",
                ),
            )

        with (
            patch(
                "app.services.ai_gateway.call_upstream_llm_detailed",
                side_effect=fake_call_upstream,
            ),
            patch.object(proxy.quota_mgr, "check_quota", return_value=(True, None)),
            patch.object(proxy.cache_mgr, "get", return_value=None),
            patch.object(proxy.cache_mgr, "set", return_value=True),
        ):
            resp = await proxy.chat_completions(
                tenant_id="test-tenant", request=request
            )

        assert resp.choices[0]["message"]["content"] == "Gateway final reply"
        assert "messages" in captured_kwargs
        sent_messages: list[ChatMessage] = captured_kwargs["messages"]
        assert len(sent_messages) == 4
        assert [m.role for m in sent_messages] == [
            "system",
            "user",
            "assistant",
            "user",
        ]
        assert sent_messages[0].content == "System instruction"
        assert sent_messages[1].content == "Turn 1"
        assert sent_messages[2].content == "Reply 1"
        assert sent_messages[3].content == "Turn 2"


# ==============================================================================
# 9. Agent Backend Structured Messages Preservation Tests
# ==============================================================================


class TestAgentBackendStructuredMessages:
    """Validate that JakeAIBackend constructs and passes structured ChatMessage objects."""

    @pytest.mark.asyncio
    async def test_jakeai_backend_dispatches_structured_messages(self) -> None:
        from app.agent.backends.base import AgentMessage, BackendRequest
        from app.agent.backends.jakeai import JakeAIBackend
        from app.providers.base import ProviderCacheTelemetry, UpstreamLLMResponse

        backend = JakeAIBackend(default_model="gemini-1.5-flash")
        agent_messages = [
            AgentMessage(role="system", content="Agent instructions"),
            AgentMessage(role="user", content="Research MSFT"),
            AgentMessage(role="assistant", content="Calling tool..."),
            AgentMessage(
                role="tool",
                content="MSFT stock data",
                name="stock_tool",
                tool_call_id="call_msft_456",
            ),
        ]
        req = BackendRequest(
            messages=agent_messages,
            tenant_id="tenant-agent",
            model="gemini-1.5-flash",
        )

        captured_kwargs: dict[str, Any] = {}

        async def fake_call_upstream(**kwargs: Any) -> Any:
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return UpstreamLLMResponse(
                text="MSFT analysis complete",
                model="gemini-1.5-flash",
                provider="gemini",
                telemetry=ProviderCacheTelemetry(
                    is_cache_eligible=False,
                    cache_hit=False,
                    cached_tokens=0,
                    uncached_input_tokens=150,
                    output_tokens=30,
                    provider="gemini",
                    model="gemini-1.5-flash",
                ),
            )

        with patch(
            "app.agent.backends.jakeai.call_upstream_llm_detailed",
            side_effect=fake_call_upstream,
        ):
            resp = await backend.generate(req)

        assert resp.content == "MSFT analysis complete"
        assert "messages" in captured_kwargs
        sent_messages: list[ChatMessage] = captured_kwargs["messages"]
        assert len(sent_messages) == 4
        assert sent_messages[0].role == "system"
        assert sent_messages[1].role == "user"
        assert sent_messages[2].role == "assistant"
        assert sent_messages[3].role == "tool"
        assert sent_messages[3].name == "stock_tool"
        assert sent_messages[3].tool_call_id == "call_msft_456"


# ==============================================================================
# 10. Direct Formatter Helper Tests
# ==============================================================================


class TestDirectFormatterFunctions:
    """Validate direct invocation of canonical format helper functions."""

    def test_direct_format_openai_with_and_without_messages(self) -> None:
        req_with = ProviderRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="Direct prompt")],
        )
        res_with = format_openai_chat_messages(req_with, default_system="Default sys")
        assert any(
            m["role"] == "user" and m["content"] == "Direct prompt" for m in res_with
        )

        req_without = ProviderRequest(model="gpt-4o", prompt="Direct prompt")
        res_without = format_openai_chat_messages(
            req_without, default_system="Default sys"
        )
        assert any(
            m["role"] == "user" and m["content"] == "Direct prompt" for m in res_without
        )

    def test_direct_format_anthropic_with_and_without_messages(self) -> None:
        req_with = ProviderRequest(
            model="claude-3-5-sonnet",
            messages=[ChatMessage(role="user", content="Direct prompt")],
        )
        sys_with, msgs_with = format_anthropic_chat_messages(
            req_with, default_system="Default sys"
        )
        assert sys_with == "Default sys"
        assert msgs_with[0]["content"] == "Direct prompt"

        req_without = ProviderRequest(model="claude-3-5-sonnet", prompt="Direct prompt")
        sys_without, msgs_without = format_anthropic_chat_messages(
            req_without, default_system="Default sys"
        )
        assert sys_without == "Default sys"
        assert msgs_without[0]["content"] == "Direct prompt"

    def test_direct_format_gemini_with_and_without_messages(self) -> None:
        req_with = ProviderRequest(
            model="gemini-1.5-flash",
            messages=[ChatMessage(role="user", content="Direct prompt")],
        )
        sys_with, contents_with = format_gemini_chat_contents(
            req_with, default_system="Default sys"
        )
        assert sys_with == "Default sys"
        assert contents_with[0]["parts"][0]["text"] == "Direct prompt"

        req_without = ProviderRequest(model="gemini-1.5-flash", prompt="Direct prompt")
        sys_without, contents_without = format_gemini_chat_contents(
            req_without, default_system="Default sys"
        )
        assert sys_without == "Default sys"
        assert contents_without[0]["parts"][0]["text"] == "Direct prompt"
