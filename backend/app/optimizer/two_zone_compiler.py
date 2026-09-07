"""Two-Zone Prompt Compiler aliases and interoperability layer.

Harmonizes CompiledPrompt with PromptEnvelope and TwoZonePromptCompiler with PromptCompiler.
"""

from __future__ import annotations

from app.optimizer.prompt_compiler import (
    ContaminationError,
    PromptCompiler,
    PromptEnvelope,
    get_prompt_compiler,
)

# Interoperability aliases matching Tier 5 architectural specifications
CompiledPrompt = PromptEnvelope
TwoZonePromptCompiler = PromptCompiler
get_two_zone_compiler = get_prompt_compiler

__all__ = [
    "CompiledPrompt",
    "ContaminationError",
    "PromptCompiler",
    "PromptEnvelope",
    "TwoZonePromptCompiler",
    "get_prompt_compiler",
    "get_two_zone_compiler",
]
