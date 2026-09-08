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