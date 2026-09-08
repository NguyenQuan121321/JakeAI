"""Regression tests for TASK-R1-02 / PROV-02: Structured Multi-Turn Messages in ProviderRequest.

Validates:
1. ProviderRequest accepts `messages: list[ChatMessage] | None = None`.
2. All 6 provider adapters (OpenAI, Anthropic, Gemini, Groq, DeepSeek, OpenRouter)
   preserve structured multi-turn conversation roles (user, assistant, tool).
3. Adapters fall back gracefully to `prompt` when `messages` is None.
"""

from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ChatMessage, ProviderRequest
from app.providers.deepseek import DeepSeekAdapter
from app.providers.gemini import GeminiAdapter
from app.providers.groq import GroqAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter


def test_openai_adapter_multiturn() -> None:
    """Verify OpenAIAdapter serializes multi-turn message history with native roles."""
    adapter = OpenAIAdapter()
    history = [
        ChatMessage(role="user", content="Hi"),
        ChatMessage(role="assistant", content="Hello! How can I help?"),
        ChatMessage(role="user", content="What did I just say?"),
    ]
    req = ProviderRequest(
        model="gpt-4o",
        prompt="What did I just say?",
        messages=history,
        system_instruction="You are a helpful bot.",
    )
    _headers, payload = adapter._prepare_payload(req, stream=False)

    msgs = payload["messages"]
    # Check that system instruction and all 3 turns are present
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "You are a helpful bot."
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Hi"
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"] == "Hello! How can I help?"
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "What did I just say?"


def test_anthropic_adapter_multiturn() -> None:
    """Verify AnthropicAdapter serializes multi-turn message history with native roles."""
    adapter = AnthropicAdapter()
    history = [
        ChatMessage(role="user", content="Hi"),
        ChatMessage(role="assistant", content="Hello! How can I help?"),
        ChatMessage(role="user", content="What did I just say?"),
    ]
    req = ProviderRequest(
        model="claude-3-5-sonnet",
        prompt="What did I just say?",
        messages=history,
        system_instruction="You are a helpful bot.",
    )
    _headers, payload = adapter._prepare_payload(req, stream=False)

    msgs = payload["messages"]
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hi"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Hello! How can I help?"
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == "What did I just say?"


def test_gemini_adapter_multiturn() -> None:
    """Verify GeminiAdapter serializes multi-turn message history using Gemini roles (user, model)."""
    adapter = GeminiAdapter()
    history = [
        ChatMessage(role="user", content="Hi"),
        ChatMessage(role="assistant", content="Hello! How can I help?"),
        ChatMessage(role="user", content="What did I just say?"),
    ]
    req = ProviderRequest(
        model="gemini-1.5-flash",
        prompt="What did I just say?",
        messages=history,
        system_instruction="You are a helpful bot.",
    )
    _model_name, payload = adapter._prepare_payload(req)

    contents = payload["contents"]
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Hi"
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["text"] == "Hello! How can I help?"
    assert contents[2]["role"] == "user"
    assert contents[2]["parts"][0]["text"] == "What did I just say?"


def test_groq_adapter_multiturn() -> None:
    """Verify GroqAdapter serializes multi-turn message history with native roles."""
    adapter = GroqAdapter()
    history = [
        ChatMessage(role="user", content="Hi"),
        ChatMessage(role="assistant", content="Hello! How can I help?"),
        ChatMessage(role="user", content="What did I just say?"),
    ]
    req = ProviderRequest(
        model="llama-3.3-70b-versatile",
        prompt="What did I just say?",
        messages=history,
        system_instruction="You are a helpful bot.",
    )
    _headers, payload = adapter._prepare_payload(req, stream=False)

    msgs = payload["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Hi"
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"] == "Hello! How can I help?"
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "What did I just say?"


def test_deepseek_adapter_multiturn() -> None:
    """Verify DeepSeekAdapter serializes multi-turn message history with native roles."""
    adapter = DeepSeekAdapter()
    history = [
        ChatMessage(role="user", content="Hi"),
        ChatMessage(role="assistant", content="Hello! How can I help?"),
        ChatMessage(role="user", content="What did I just say?"),
    ]
    req = ProviderRequest(
        model="deepseek-chat",
        prompt="What did I just say?",
        messages=history,
        system_instruction="You are a helpful bot.",
    )
    _headers, payload = adapter._prepare_payload(req, stream=False)

    msgs = payload["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Hi"
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"] == "Hello! How can I help?"
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "What did I just say?"


def test_openrouter_adapter_multiturn() -> None:
    """Verify OpenRouterAdapter serializes multi-turn message history with native roles."""
    adapter = OpenRouterAdapter()
    history = [
        ChatMessage(role="user", content="Hi"),
        ChatMessage(role="assistant", content="Hello! How can I help?"),
        ChatMessage(role="user", content="What did I just say?"),
    ]
    req = ProviderRequest(
        model="openai/gpt-4o",
        prompt="What did I just say?",
        messages=history,
        system_instruction="You are a helpful bot.",
    )
    _headers, payload = adapter._prepare_payload(req, stream=False)

    msgs = payload["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Hi"
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"] == "Hello! How can I help?"
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "What did I just say?"
