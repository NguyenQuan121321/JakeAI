"""Unit tests for TASK RAG-02: Unicode NFKC and text normalization."""

from app.rag.normalizer import normalize_text


def test_unicode_nfkc_normalization() -> None:
    """Verify NFKC decomposes ligatures and normalizes full-width forms."""
    # Ligature 'fi' (\ufb01) -> 'fi'
    ligature_input = "The pro\ufb01t margin is high."
    normalized = normalize_text(ligature_input)
    assert normalized == "The profit margin is high."

    # Full-width digits and currency normalization test
    full_width = "Revenue: \uff04\uff11\uff15\uff10\uff0c\uff10\uff10\uff10"
    normalized_fw = normalize_text(full_width)
    assert normalized_fw == "Revenue: $150,000"


def test_line_ending_normalization() -> None:
    """Verify CRLF (Windows) and CR (old Mac) are normalized to LF."""
    raw = "Line 1\r\nLine 2\rLine 3\nLine 4"
    normalized = normalize_text(raw)
    assert "\r" not in normalized
    assert normalized == "Line 1\nLine 2\nLine 3\nLine 4"


def test_control_character_stripping() -> None:
    """Verify non-printable control characters are removed while preserving \t and \n."""
    raw = "Hello\x00\x07World\t\x1bTest\nData\x7fDone"
    normalized = normalize_text(raw)
    # \x00, \x07, \x1b, \x7f should be removed; \t and \n preserved
    assert "\x00" not in normalized
    assert "\x07" not in normalized
    assert "\x1b" not in normalized
    assert "\x7f" not in normalized
    assert "Hello" in normalized
    assert "World" in normalized
    assert "\t" in normalized
    assert "\n" in normalized


def test_code_block_preservation() -> None:
    """Verify prose whitespace is collapsed while code block indentation is preserved."""
    input_text = (
        "Here    is   some   prose   with    redundant     spaces.\n\n\n\n"
        "```python\n"
        "def compute(x):\n"
        "    # Indentation of 4 spaces must be preserved\n"
        "    return x * 2\n"
        "```\n\n"
        "Another   paragraph   here."
    )
    normalized = normalize_text(input_text)

    # Prose spaces collapsed
    assert "Here is some prose with redundant spaces." in normalized
    assert "Another paragraph here." in normalized
    # Excessive newlines collapsed
    assert "\n\n\n" not in normalized

    # Code block preserved intact
    assert (
        "```python\ndef compute(x):\n    # Indentation of 4 spaces must be preserved\n    return x * 2\n```"
        in normalized
    )
