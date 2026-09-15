"""Unit tests for multi-provider request normalization and message serialization (UNIT-058).

Covers:
1. ProviderRequest._validate_and_sync_prompt: automated prompt and system instruction sync.
2. format_openai_chat_messages: system extraction, roles, tool_calls, tool_call_id, and fallbacks.
3. format_anthropic_chat_messages: system separation, alternating turns, tool_result blocks, consecutive user merging.
4. format_gemini_chat_contents: systemInstruction separation, functionCall / functionResponse mapping.
5. Boundary conditions: empty messages, None content, missing tool call IDs, compiled two-zone prompts.
"""

from __future__ import annotations

from app.optimizer.two_zone_compiler import TwoZonePromptCompiler
from app.providers.base import (
    ChatMessage,
    ProviderRequest,
    format_anthropic_chat_messages,
    format_gemini_chat_contents,
    format_openai_chat_messages,
)

# ==============================================================================
# 1. ProviderRequest Validation & Prompt Synchronization
# ==============================================================================


def test_provider_request_syncs_prompt_from_messages() -> None:
    """When prompt is omitted, the last user message content is synchronized into prompt."""
    req = ProviderRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="system", content="System instruction"),
            ChatMessage(role="user", content="Turn 1 user"),
            ChatMessage(role="assistant", content="Turn 1 reply"),
            ChatMessage(role="user", content="Turn 2 user query"),
        ],
    )
    assert req.prompt == "Turn 2 user query"
    assert req.system_instruction == "System instruction"


def test_provider_request_preserves_explicit_prompt_and_system() -> None:
    """Explicitly provided prompt and system_instruction are never overridden by messages."""
    req = ProviderRequest(
        model="gpt-4o",
        prompt="Explicit prompt",
        system_instruction="Explicit system",
        messages=[
            ChatMessage(role="system", content="Other system"),
            ChatMessage(role="user", content="Other user"),
        ],
    )
    assert req.prompt == "Explicit prompt"
    assert req.system_instruction == "Explicit system"


def test_provider_request_empty_messages_leaves_defaults() -> None:
    """Empty or None messages leave prompt and system_instruction as defaults."""
    req = ProviderRequest(model="gpt-4o", prompt="hello")
    assert req.prompt == "hello"
    assert req.system_instruction is None


# ==============================================================================
# 2. format_openai_chat_messages
# ==============================================================================


def test_format_openai_chat_messages_full_conversation() -> None:
    """Transforms all canonical roles (system, developer, user, assistant, tool) into OpenAI format."""
    req = ProviderRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="developer", content="Internal developer guidelines"),
            ChatMessage(role="user", content="Execute action", name="alice"),
            ChatMessage(
                role="assistant",
                content="Calling tool",
                tool_calls=[
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "calculator", "arguments": '{"x": 2}'},
                    }
                ],
            ),
            ChatMessage(
                role="tool",
                content="4",
                tool_call_id="call_123",
                name="calculator",
            ),
            ChatMessage(role="assistant", content="Result is 4"),
        ],
    )

    formatted = format_openai_chat_messages(req, default_system="Default Sys")
    assert len(formatted) == 5

    assert formatted[0] == {
        "role": "developer",
        "content": "Internal developer guidelines",
    }
    assert formatted[1] == {
        "role": "user",
        "content": "Execute action",
        "name": "alice",
    }
    assert formatted[2]["role"] == "assistant"
    assert formatted[2]["content"] == "Calling tool"
    assert formatted[2]["tool_calls"][0]["id"] == "call_123"
    assert formatted[3] == {
        "role": "tool",
        "content": "4",
        "tool_call_id": "call_123",
        "name": "calculator",
    }
    assert formatted[4] == {"role": "assistant", "content": "Result is 4"}


def test_format_openai_chat_messages_injects_system_when_missing() -> None:
    """When messages lack system/developer turn, injects system_instruction or default_system."""
    req = ProviderRequest(
        model="gpt-4o",
        system_instruction="Enforced system prompt",
        messages=[ChatMessage(role="user", content="Hello")],
    )

    formatted = format_openai_chat_messages(req)
    assert len(formatted) == 2
    assert formatted[0] == {"role": "system", "content": "Enforced system prompt"}
    assert formatted[1] == {"role": "user", "content": "Hello"}


def test_format_openai_chat_messages_fallback_without_messages() -> None:
    """Without messages list, generates system + user messages from compiled/prompt."""
    compiled = TwoZonePromptCompiler().compile(
        system_instruction="Static Zone 1 Prefix",
        user_query="Dynamic Zone 2 Query",
    )
    req = ProviderRequest(model="gpt-4o", prompt="Raw query")

    formatted = format_openai_chat_messages(req, compiled=compiled)
    assert len(formatted) == 2
    assert formatted[0] == {"role": "system", "content": "Static Zone 1 Prefix"}
    assert formatted[1] == {"role": "user", "content": "Dynamic Zone 2 Query"}


# ==============================================================================
# 3. format_anthropic_chat_messages
# ==============================================================================


def test_format_anthropic_chat_messages_system_separation_and_tool_results() -> None:
    """Anthropic separates system text, transforms tool role to tool_result blocks."""
    req = ProviderRequest(
        model="claude-3-5-sonnet",
        messages=[
            ChatMessage(role="system", content="You are Claude."),
            ChatMessage(role="user", content="Search finance"),
            ChatMessage(
                role="assistant",
                content="Searching...",
                tool_calls=[
                    {
                        "id": "toolu_abc",
                        "type": "function",
                        "function": {
                            "name": "search_db",
                            "arguments": {"query": "revenue"},
                        },
                    }
                ],
            ),
            ChatMessage(
                role="tool",
                content='{"revenue": 1000}',
                tool_call_id="toolu_abc",
            ),
        ],
    )

    sys_text, messages = format_anthropic_chat_messages(req)
    assert sys_text == "You are Claude."
    # Non-system messages
    assert len(messages) == 3

    # Turn 0: user query
    assert messages[0] == {"role": "user", "content": "Search finance"}

    # Turn 1: assistant tool_use blocks
    assert messages[1]["role"] == "assistant"
    asst_blocks = messages[1]["content"]
    assert asst_blocks[0] == {"type": "text", "text": "Searching..."}
    assert asst_blocks[1]["type"] == "tool_use"
    assert asst_blocks[1]["id"] == "toolu_abc"
    assert asst_blocks[1]["name"] == "search_db"

    # Turn 2: tool result block inside user turn
    assert messages[2]["role"] == "user"
    tool_blocks = messages[2]["content"]
    assert tool_blocks[0]["type"] == "tool_result"
    assert tool_blocks[0]["tool_use_id"] == "toolu_abc"
    assert tool_blocks[0]["content"] == '{"revenue": 1000}'


def test_format_anthropic_merges_consecutive_user_messages() -> None:
    """Anthropic requires alternating roles; consecutive user turns must be merged."""
    req = ProviderRequest(
        model="claude-3-5-sonnet",
        messages=[
            ChatMessage(role="user", content="Part 1 of prompt"),
            ChatMessage(role="user", content="Part 2 of prompt"),
            ChatMessage(role="assistant", content="Understood"),
        ],
    )

    _, messages = format_anthropic_chat_messages(req)
    # Consecutive user messages merged into single turn
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert "Part 1 of prompt\nPart 2 of prompt" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"


def test_format_anthropic_fallback_without_messages() -> None:
    """Without messages, creates single user message and extracts system instruction."""
    req = ProviderRequest(
        model="claude-3-5-sonnet",
        prompt="Tell me a joke",
        system_instruction="Be concise",
    )
    sys_text, messages = format_anthropic_chat_messages(req)
    assert sys_text == "Be concise"
    assert len(messages) == 1
    assert messages[0] == {"role": "user", "content": "Tell me a joke"}


# ==============================================================================
# 4. format_gemini_chat_contents
# ==============================================================================


def test_format_gemini_chat_contents_functions() -> None:
    """Gemini formats systemInstruction, user/model parts, and functionResponse."""
    req = ProviderRequest(
        model="gemini-1.5-pro",
        messages=[
            ChatMessage(role="system", content="Gemini system rule"),
            ChatMessage(role="user", content="Check stock"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    {
                        "id": "call_stock_1",
                        "type": "function",
                        "function": {
                            "name": "get_quote",
                            "arguments": {"symbol": "AAPL"},
                        },
                    }
                ],
            ),
            ChatMessage(
                role="tool",
                content='{"price": 150.0}',
                tool_call_id="call_stock_1",
            ),
        ],
    )

    sys_text, contents = format_gemini_chat_contents(req)
    assert sys_text == "Gemini system rule"
    assert len(contents) == 3

    # Turn 0: user text
    assert contents[0] == {"role": "user", "parts": [{"text": "Check stock"}]}

    # Turn 1: model functionCall
    assert contents[1]["role"] == "model"
    part1 = contents[1]["parts"][0]
    assert "functionCall" in part1
    assert part1["functionCall"]["name"] == "get_quote"

    # Turn 2: functionResponse
    assert contents[2]["role"] == "function"
    part2 = contents[2]["parts"][0]
    assert "functionResponse" in part2
    assert part2["functionResponse"]["name"] == "get_quote"
    assert part2["functionResponse"]["response"] == {"result": '{"price": 150.0}'}


def test_format_gemini_fallback_without_messages() -> None:
    """Without messages, creates user parts and returns system instruction."""
    req = ProviderRequest(
        model="gemini-1.5-pro",
        prompt="Explain quantum entanglement",
        system_instruction="You are a physics professor",
    )
    sys_text, contents = format_gemini_chat_contents(req)
    assert sys_text == "You are a physics professor"
    assert len(contents) == 1
    assert contents[0] == {
        "parts": [{"text": "Explain quantum entanglement"}],
    }
