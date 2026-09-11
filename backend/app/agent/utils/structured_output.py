"""Canonical structured model output parsing utility for JakeAI Orchestration.

Extracts structured JSON dictionary objects from model responses conforming strictly to:
1. Empty input validation
2. Raw JSON object parsing
3. ```json fenced code block extraction
4. Generic ``` fenced code block extraction
5. Bounded embedded JSON object extraction
6. None fallback for malformed or non-dictionary data

No arbitrary code execution (no eval, no exec).
Catches specifically json.JSONDecodeError without broad exception swallowing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Bounded regex matching an embedded JSON object with balanced non-nested or single-level nested content
_BOUNDED_OBJECT_PATTERN = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")


def extract_json_dict(text: str) -> dict[str, Any] | None:
    """Extract one JSON dictionary object from model text response.

    Returns a valid Python dictionary if an object can be extracted and parsed,
    or None if the text is empty, malformed, non-dictionary JSON, or unclosed fence.
    """
    # 1. Empty / whitespace-only input
    if not text or not text.strip():
        return None

    text_clean = text.strip()

    # 2. Raw JSON object (or reject top-level non-dict JSON)
    if text_clean.startswith("{") and text_clean.endswith("}"):
        try:
            data = json.loads(text_clean)
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError:
            pass

    # Reject top-level array or primitives immediately if entire input is non-dict
    if text_clean.startswith("[") and text_clean.endswith("]"):
        try:
            data = json.loads(text_clean)
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError:
            pass

    if text_clean in ("true", "false", "null") or text_clean.isdigit():
        return None

    if text_clean.startswith('"') and text_clean.endswith('"'):
        try:
            json.loads(text_clean)
            return None
        except json.JSONDecodeError:
            pass

    # 3. ```json fenced block
    if "```json" in text:
        start_marker = "```json"
        start_idx = text.find(start_marker) + len(start_marker)
        end_idx = text.find("```", start_idx)
        if end_idx == -1:
            # Missing closing fence: model output is truncated or malformed
            return None
        block_content = text[start_idx:end_idx].strip()
        try:
            data = json.loads(block_content)
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError:
            return None

    # 4. Generic ``` fenced block
    if "```" in text:
        start_marker = "```"
        start_idx = text.find(start_marker) + len(start_marker)
        end_idx = text.find("```", start_idx)
        if end_idx == -1:
            # Missing closing fence: model output is truncated or malformed
            return None
        block_content = text[start_idx:end_idx].strip()
        # Strip optional language tag on first line (e.g. ```text or ```json)
        if "\n" in block_content and not block_content.startswith("{"):
            first_line, rest = block_content.split("\n", 1)
            if first_line.strip().isalnum():
                block_content = rest.strip()
        try:
            data = json.loads(block_content)
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError:
            return None

    # 5. Embedded JSON object discovered by bounded regex
    # First attempt: outer { ... } candidate
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        outer_candidate = text[first_brace : last_brace + 1]
        try:
            data = json.loads(outer_candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Second attempt: bounded pattern search for cases with braces in surrounding prose
    for match in _BOUNDED_OBJECT_PATTERN.finditer(text):
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    # Fallback attempt: scan balanced braces linearly (zero regex backtracking risk)
    if first_brace != -1:
        idx = first_brace
        while idx != -1:
            depth = 0
            in_str = False
            escape = False
            for i in range(idx, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    if in_str:
                        escape = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[idx : i + 1]
                            try:
                                data = json.loads(candidate)
                                if isinstance(data, dict):
                                    return data
                            except json.JSONDecodeError:
                                pass
                            break
            idx = text.find("{", idx + 1)

    # 6. Return None
    return None
