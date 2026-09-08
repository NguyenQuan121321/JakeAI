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
            prompt="Explicit prompt",
            messages=msgs,
        )
        assert req.prompt == "Explicit prompt"
        assert req.messages == msgs

    def test_chat_message_dict_initialization(self) -> None:
        """ChatMessage supports full attribute schema and tool calls."""
        msg = ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "lookup_stock",
                        "arguments": '{"ticker": "MSFT"}',
                    },
                }
            ],
        )
        assert msg.role == "assistant"
        assert msg.content is None
        assert msg.tool_calls is not None
        assert msg.tool_calls[0]["id"] == "call_123"


# ==============================================================================
# 2. 5-Turn Conversation Contract Tests
# ==============================================================================


class TestFiveTurnConversation:
    """Validate 5-turn multi-turn conversation preservation across all adapters."""

    @pytest.fixture
    def five_turn_messages(self) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content="You are a financial assistant."),
            ChatMessage(
                role="user", content="Turn 1: What is Apple's primary revenue?"
            ),
            ChatMessage(
                role="assistant",
                content="Turn 2: Apple's primary revenue is the iPhone.",
            ),
            ChatMessage(
                role="user", content="Turn 3: What percentage of revenue is that?"
            ),
            ChatMessage(
                role="assistant",
                content="Turn 4: It accounts for approximately 50% of revenue.",
            ),
            ChatMessage(role="user", content="Turn 5: What about Services growth?"),
        ]

    def test_5_turn_openai_adapter(self, five_turn_messages: list[ChatMessage]) -> None:
        adapter = OpenAIAdapter()
        req = ProviderRequest(
            model="gpt-4o",
            messages=five_turn_messages,
        )
        _headers, payload = adapter._prepare_payload(req)
        msgs = payload["messages"]
        assert len(msgs) == 6
        assert msgs[0] == {
            "role": "system",
            "content": "You are a financial assistant.",
        }
        assert msgs[1] == {
            "role": "user",
            "content": "Turn 1: What is Apple's primary revenue?",
        }
        assert msgs[2] == {
            "role": "assistant",
            "content": "Turn 2: Apple's primary revenue is the iPhone.",
        }
        assert msgs[3] == {
            "role": "user",
            "content": "Turn 3: What percentage of revenue is that?",
        }
        assert msgs[4] == {
            "role": "assistant",
            "content": "Turn 4: It accounts for approximately 50% of revenue.",
        }
        assert msgs[5] == {
            "role": "user",
            "content": "Turn 5: What about Services growth?",
        }

    def test_5_turn_anthropic_adapter(
        self, five_turn_messages: list[ChatMessage]
    ) -> None:
        adapter = AnthropicAdapter()
        req = ProviderRequest(
            model="claude-3-5-sonnet-20241022",
            messages=five_turn_messages,
        )
        _headers, payload = adapter._prepare_payload(req)
        # System instruction isolated in system block
        assert payload["system"][0]["text"] == "You are a financial assistant."
        # Remaining 5 turns alternate user/assistant
        msgs = payload["messages"]
        assert len(msgs) == 5
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Turn 1: What is Apple's primary revenue?"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Turn 2: Apple's primary revenue is the iPhone."
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"] == "Turn 3: What percentage of revenue is that?"
        assert msgs[3]["role"] == "assistant"
        assert (
            msgs[3]["content"]
            == "Turn 4: It accounts for approximately 50% of revenue."
        )
        assert msgs[4]["role"] == "user"
        assert msgs[4]["content"] == "Turn 5: What about Services growth?"

    def test_5_turn_gemini_adapter(self, five_turn_messages: list[ChatMessage]) -> None:
        adapter = GeminiAdapter()
        req = ProviderRequest(
            model="gemini-1.5-pro",
            messages=five_turn_messages,
        )
        _model_name, payload = adapter._prepare_payload(req)
        # System instruction in systemInstruction
        assert (
            payload["systemInstruction"]["parts"][0]["text"]
            == "You are a financial assistant."
        )
        # 5 non-system turns mapped to user and model
        contents = payload["contents"]
        assert len(contents) == 5
        assert contents[0]["role"] == "user"
        assert (
            contents[0]["parts"][0]["text"]
            == "Turn 1: What is Apple's primary revenue?"
        )
        assert contents[1]["role"] == "model"
        assert (
            contents[1]["parts"][0]["text"]
            == "Turn 2: Apple's primary revenue is the iPhone."
        )
        assert contents[2]["role"] == "user"
        assert (
            contents[2]["parts"][0]["text"]
            == "Turn 3: What percentage of revenue is that?"
        )
        assert contents[3]["role"] == "model"
        assert (
            contents[3]["parts"][0]["text"]
            == "Turn 4: It accounts for approximately 50% of revenue."
        )
        assert contents[4]["role"] == "user"
        assert contents[4]["parts"][0]["text"] == "Turn 5: What about Services growth?"

    def test_5_turn_deepseek_adapter(
        self, five_turn_messages: list[ChatMessage]
    ) -> None:
        adapter = DeepSeekAdapter()
        req = ProviderRequest(
            model="deepseek-chat",
            messages=five_turn_messages,
        )
        _headers, payload = adapter._prepare_payload(req)
        msgs = payload["messages"]
        assert len(msgs) == 6
        assert msgs[2]["role"] == "assistant"
        assert msgs[4]["role"] == "assistant"

    def test_5_turn_groq_adapter(self, five_turn_messages: list[ChatMessage]) -> None:
        adapter = GroqAdapter()
        req = ProviderRequest(
            model="llama-3.3-70b-versatile",
            messages=five_turn_messages,
        )
        _headers, payload = adapter._prepare_payload(req)
        msgs = payload["messages"]
        assert len(msgs) == 6
        assert msgs[2]["role"] == "assistant"
        assert msgs[4]["role"] == "assistant"

    def test_5_turn_openrouter_adapter(
        self, five_turn_messages: list[ChatMessage]
    ) -> None:
        adapter = OpenRouterAdapter()
        req = ProviderRequest(
            model="anthropic/claude-3.5-sonnet",
            messages=five_turn_messages,
        )
        _headers, payload = adapter._prepare_payload(req)
        msgs = payload["messages"]
        assert len(msgs) == 6
        assert msgs[2]["role"] == "assistant"
        assert msgs[4]["role"] == "assistant"


# ==============================================================================
# 3. Assistant Recall Tests
# ==============================================================================


class TestAssistantRecallPreservation:
    """Verify that assistant turns are distinctly preserved and never merged/lost."""

    def test_assistant_recall_across_turns(self) -> None:
        req = ProviderRequest(
            model="gpt-4o",
            messages=[
                ChatMessage(role="user", content="My lucky number is 42."),
                ChatMessage(
                    role="assistant",
                    content="I have noted that your lucky number is 42.",
                ),
                ChatMessage(role="user", content="What was my lucky number?"),
            ],
        )
        formatted = format_openai_chat_messages(
            req, default_system="You are a helpful assistant."
        )
        # Verify 3 separate messages, with assistant turn intact
        assert len(formatted) == 4  # Includes default system + 3 turns
        roles = [m["role"] for m in formatted]
        assert roles == ["system", "user", "assistant", "user"]
        assert formatted[2]["content"] == "I have noted that your lucky number is 42."

    def test_anthropic_assistant_recall(self) -> None:
        req = ProviderRequest(
            model="claude-3-5-sonnet-20241022",
            messages=[
                ChatMessage(role="user", content="My favorite stock is NVDA."),
                ChatMessage(role="assistant", content="Got it, NVDA."),
                ChatMessage(role="user", content="What was my stock?"),
            ],
        )
        _, msgs = format_anthropic_chat_messages(req)
        assert len(msgs) == 3
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Got it, NVDA."

    def test_gemini_assistant_recall(self) -> None:
        req = ProviderRequest(
            model="gemini-1.5-flash",
            messages=[
                ChatMessage(role="user", content="Code: 9988"),
                ChatMessage(role="assistant", content="Code 9988 recorded."),
                ChatMessage(role="user", content="Repeat code."),
            ],
        )
        _, contents = format_gemini_chat_contents(req)
        assert len(contents) == 3
        assert contents[1]["role"] == "model"
        assert contents[1]["parts"][0]["text"] == "Code 9988 recorded."


# ==============================================================================
# 4. System Instruction Preservation Tests
# ==============================================================================


class TestSystemInstructionPreservation:
    """Verify system instructions are preserved and not duplicated or dropped."""

    def test_system_message_in_messages_list_not_duplicated_openai(self) -> None:
        req = ProviderRequest(
            model="gpt-4o",
            messages=[
                ChatMessage(role="system", content="Custom system rule A."),
                ChatMessage(role="user", content="Hi"),
            ],
            system_instruction="Ignored default if already in messages",
        )
        formatted = format_openai_chat_messages(req)
        # Should have exactly 1 system message, not 2
        system_msgs = [m for m in formatted if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "Custom system rule A."

    def test_system_instruction_injected_when_not_in_messages_openai(self) -> None:
        req = ProviderRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="Hello")],
            system_instruction="System rule via field",
        )
        formatted = format_openai_chat_messages(req)
        assert formatted[0]["role"] == "system"
        assert formatted[0]["content"] == "System rule via field"
        assert formatted[1]["role"] == "user"

    def test_system_instruction_extracted_anthropic(self) -> None:
        req = ProviderRequest(
            model="claude-3-5-sonnet",
            messages=[
                ChatMessage(role="system", content="System instruction for Anthropic"),
                ChatMessage(role="user", content="Query"),
            ],
        )
        system_text, msgs = format_anthropic_chat_messages(req)
        assert system_text == "System instruction for Anthropic"
        # System turn must NOT appear in messages array
        assert all(m["role"] != "system" for m in msgs)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_system_instruction_extracted_gemini(self) -> None:
        req = ProviderRequest(
            model="gemini-1.5-flash",
            messages=[
                ChatMessage(role="system", content="System instruction for Gemini"),
                ChatMessage(role="user", content="Hello"),
            ],
        )
        system_text, contents = format_gemini_chat_contents(req)
        assert system_text == "System instruction for Gemini"
        # System turn must NOT appear in contents array
        assert all(c["role"] != "system" for c in contents)
        assert len(contents) == 1
        assert contents[0]["role"] == "user"


# ==============================================================================
# 5. Tool Message & Tool Call ID Preservation Tests
# ==============================================================================


class TestToolMessagePreservation:
    """Verify tool calls, tool results, and tool call IDs are preserved across providers."""

    @pytest.fixture
    def tool_conversation(self) -> list[ChatMessage]:
        return [
            ChatMessage(role="user", content="Fetch ticker AAPL"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    {
                        "id": "call_aapl_001",
                        "type": "function",
                        "function": {
                            "name": "get_quote",
                            "arguments": json.dumps({"ticker": "AAPL"}),
                        },
                    }
                ],
            ),
            ChatMessage(
                role="tool",
                content='{"price": 230.50, "currency": "USD"}',
                tool_call_id="call_aapl_001",
                name="get_quote",
            ),
            ChatMessage(
                role="assistant",
                content="Apple is currently trading at $230.50.",
            ),
            ChatMessage(role="user", content="Thank you!"),
        ]

    def test_tool_preservation_openai(
        self, tool_conversation: list[ChatMessage]
    ) -> None:
        req = ProviderRequest(
            model="gpt-4o",
            messages=tool_conversation,
        )
        formatted = format_openai_chat_messages(req)
        # Find assistant message with tool calls
        asst_call = next(
            m for m in formatted if m["role"] == "assistant" and "tool_calls" in m
        )
        assert asst_call["tool_calls"][0]["id"] == "call_aapl_001"
        assert asst_call["tool_calls"][0]["function"]["name"] == "get_quote"

        # Find tool message
        tool_msg = next(m for m in formatted if m["role"] == "tool")
        assert tool_msg["tool_call_id"] == "call_aapl_001"
        assert tool_msg["name"] == "get_quote"
        assert "230.50" in tool_msg["content"]

    def test_tool_preservation_anthropic(
        self, tool_conversation: list[ChatMessage]
    ) -> None:
        req = ProviderRequest(
            model="claude-3-5-sonnet",
            messages=tool_conversation,
        )
        _, msgs = format_anthropic_chat_messages(req)
        # Assistant turn must have tool_use block
        asst_msg = msgs[1]
        assert asst_msg["role"] == "assistant"
        assert isinstance(asst_msg["content"], list)
        tool_use = asst_msg["content"][0]
        assert tool_use["type"] == "tool_use"
        assert tool_use["id"] == "call_aapl_001"
        assert tool_use["name"] == "get_quote"

        # Tool result turn must have tool_result block under role "user"
        tool_turn = msgs[2]
        assert tool_turn["role"] == "user"
        assert isinstance(tool_turn["content"], list)
        tool_res = tool_turn["content"][0]
        assert tool_res["type"] == "tool_result"
        assert tool_res["tool_use_id"] == "call_aapl_001"
        assert "230.50" in tool_res["content"]

    def test_tool_preservation_gemini(
        self, tool_conversation: list[ChatMessage]
    ) -> None:
        req = ProviderRequest(
            model="gemini-1.5-flash",
            messages=tool_conversation,
        )
        _, contents = format_gemini_chat_contents(req)
        # Assistant turn has functionCall part
        asst_turn = contents[1]
        assert asst_turn["role"] == "model"
        fc_part = asst_turn["parts"][0]["functionCall"]
        assert fc_part["name"] == "get_quote"
        assert fc_part["args"] == {"ticker": "AAPL"}

        # Tool turn has functionResponse part under role "function"
        tool_turn = contents[2]
        assert tool_turn["role"] == "function"
        fr_part = tool_turn["parts"][0]["functionResponse"]
        assert fr_part["name"] == "get_quote"
        assert "230.50" in fr_part["response"]["result"]


# ==============================================================================
# 6. Strict Ordering Preservation Tests
# ==============================================================================


class TestOrderingPreservation:
    """Verify that message order is strictly preserved end-to-end."""

    def test_strict_order_preservation(self) -> None:
        order_keys = [f"turn_{i}" for i in range(1, 8)]
        msgs = [
            ChatMessage(role="user", content=order_keys[0]),
            ChatMessage(role="assistant", content=order_keys[1]),
            ChatMessage(role="user", content=order_keys[2]),
            ChatMessage(role="assistant", content=order_keys[3]),
            ChatMessage(role="user", content=order_keys[4]),
            ChatMessage(role="assistant", content=order_keys[5]),
            ChatMessage(role="user", content=order_keys[6]),
        ]
        req = ProviderRequest(model="gpt-4o", messages=msgs)
        formatted = format_openai_chat_messages(req)
        # Filter out injected system message
        non_sys = [m for m in formatted if m["role"] != "system"]
        extracted_keys = [m["content"] for m in non_sys]
        assert extracted_keys == order_keys


# ==============================================================================
# 7. Backward Compatibility: Single Prompt Callers
# ==============================================================================


class TestSinglePromptBackwardCompatibility:
    """Verify single-prompt callers produce expected native payloads."""

    def test_single_prompt_openai(self) -> None:
        adapter = OpenAIAdapter()
        req = ProviderRequest(
            model="gpt-4o",
            prompt="Simple query",
            system_instruction="System instruction",
        )
        _, payload = adapter._prepare_payload(req)
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "System instruction"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "Simple query"

    def test_single_prompt_anthropic(self) -> None:
        adapter = AnthropicAdapter()
        req = ProviderRequest(
            model="claude-3-5-sonnet",
            prompt="Simple query",
            system_instruction="System instruction",
        )
        _, payload = adapter._prepare_payload(req)
        assert payload["system"][0]["text"] == "System instruction"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["content"] == "Simple query"

    def test_single_prompt_gemini(self) -> None:
        adapter = GeminiAdapter()
        req = ProviderRequest(
            model="gemini-1.5-flash",
            prompt="Simple query",
            system_instruction="System instruction",
        )
        _, payload = adapter._prepare_payload(req)
        assert payload["systemInstruction"]["parts"][0]["text"] == "System instruction"
        assert len(payload["contents"]) == 1
        assert payload["contents"][0]["parts"][0]["text"] == "Simple query"


# ==============================================================================
# 8. AI Gateway End-to-End Multi-Turn Dispatch Tests
# ==============================================================================


class TestGatewayMultiTurnDispatch:
    """Verify AI Gateway chat completions preserves structured multi-turn conversation."""

    @pytest.mark.asyncio
    async def test_gateway_forwards_structured_messages_to_upstream(self) -> None:
        quota_mgr = QuotaManager()
        proxy = GatewayInferenceProxy(quota_mgr)
        tenant_id = "tenant-structured-gw"
        await quota_mgr.set_quota_limit(tenant_id, 100_000)

        req = GatewayChatRequest(
            model="gpt-4o",
            messages=[
                ChatMessage(role="system", content="Act as a financial analyst."),
                ChatMessage(role="user", content="Turn 1: Hi"),
                ChatMessage(role="assistant", content="Turn 2: Hello, how can I help?"),
                ChatMessage(role="user", content="Turn 3: Compute CAGR"),
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "compute_cagr",
                        "description": "Calculates compound annual growth rate",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        )

        captured_kwargs: dict[str, Any] = {}

        async def mock_call_upstream_llm_detailed(**kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return None  # Let fallback generate response

        with patch(
            "app.services.ai_gateway.call_upstream_llm_detailed",
            side_effect=mock_call_upstream_llm_detailed,
        ):
            res = await proxy.chat_completions(tenant_id=tenant_id, request=req)
            assert res is not None

        # Verify structured messages were forwarded without truncation
        assert "messages" in captured_kwargs
        dispatched_messages = captured_kwargs["messages"]
        assert len(dispatched_messages) == 4
        assert dispatched_messages[0].role == "system"
        assert dispatched_messages[0].content == "Act as a financial analyst."
        assert dispatched_messages[1].role == "user"
        assert dispatched_messages[1].content == "Turn 1: Hi"
        assert dispatched_messages[2].role == "assistant"
        assert dispatched_messages[2].content == "Turn 2: Hello, how can I help?"
        assert dispatched_messages[3].role == "user"
        assert dispatched_messages[3].content == "Turn 3: Compute CAGR"

        # Verify tools were forwarded
        assert captured_kwargs["tools"] == req.tools
