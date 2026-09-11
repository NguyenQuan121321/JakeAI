"""Unicode and text normalization engine for JakeAI RAG pipeline."""

from __future__ import annotations

import re
import unicodedata

# Matches control characters excluding tab (\t) and newline (\n)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Fenced code block regex (matches ```...``` or ~~~...~~~)
FENCED_CODE_REGEX = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)")


def normalize_text(text: str, is_code_or_structured: bool = False) -> str:
    """Apply NFKC normalization, line ending conversion, and safe whitespace cleaning.

    Args:
        text: Raw input string.
        is_code_or_structured: If True, skips aggressive whitespace collapsing to
            preserve code/data indentation.

    Returns:
        Normalized text string preserving code blocks and structured formatting.
    """
    if not text:
        return ""

    # 1. Unicode NFKC Normalization
    normalized = unicodedata.normalize("NFKC", text)

    # 2. Normalize Line Endings (\r\n and \r -> \n)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Remove Invalid Control Characters (preserve \n and \t)
    normalized = CONTROL_CHAR_REGEX.sub("", normalized)

    # If the entire input is designated code or structured data, return early
    if is_code_or_structured:
        return normalized.strip()

    # 4. Normalize Accidental Whitespace Where Semantically Safe
    # Split text into code blocks vs standard text blocks to protect code blocks
    parts = FENCED_CODE_REGEX.split(normalized)

    cleaned_parts: list[str] = []
    for part in parts:
        if part.startswith("```") or part.startswith("~~~"):
            # Preserve code blocks intact
            cleaned_parts.append(part)
        else:
            # Process non-code prose safely
            lines = part.split("\n")
            cleaned_lines: list[str] = []
            for line in lines:
                # Collapse redundant horizontal spaces into a single space while preserving tabs
                cleaned_line = re.sub(r"[^\S\n\t]+", " ", line).strip(" ")
                cleaned_lines.append(cleaned_line)

            processed_text = "\n".join(cleaned_lines)
            # Collapse 3 or more consecutive newlines into 2 (paragraph break)
            processed_text = re.sub(r"\n{3,}", "\n\n", processed_text)
            cleaned_parts.append(processed_text)

    result = "".join(cleaned_parts).strip()
    return result
