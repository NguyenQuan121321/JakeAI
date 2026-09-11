"""Unit tests for RAG document parsers (PlainText, Markdown, PDF) and MIME validation."""

import io
from unittest.mock import patch

import pytest

from app.rag.parsers import (
    MarkdownParser,
    PDFParser,
    PlainTextParser,
    UnsupportedDocumentTypeError,
    get_parser,
)


def test_plain_text_parser() -> None:
    """Verify PlainTextParser handles UTF-8, Latin-1, and null byte removal."""
    parser = PlainTextParser()
    assert ".txt" in parser.supported_extensions
    assert "text/plain" in parser.supported_mime_types

    raw_bytes = b"Hello, World!\x00 This is a test."
    parsed = parser.parse_bytes(raw_bytes, filename="test.txt")

    assert "Hello, World! This is a test." in parsed.content
    assert "\x00" not in parsed.content
    assert parsed.mime_type == "text/plain"
    assert parsed.source == "test.txt"
    assert parsed.metadata["byte_size"] == len(raw_bytes)


def test_markdown_parser_headings() -> None:
    """Verify MarkdownParser extracts headings and structural text."""
    parser = MarkdownParser()
    assert ".md" in parser.supported_extensions
    assert "text/markdown" in parser.supported_mime_types

    md_content = (
        "# JakeAI Architecture\n\n"
        "JakeAI is an enterprise platform.\n\n"
        "## Core RAG Pipeline\n\n"
        "RAG pipeline uses FastEmbed and Qdrant."
    )
    parsed = parser.parse_text(md_content, filename="arch.md")

    assert "JakeAI Architecture" in parsed.metadata.get("headings", [])
    assert "Core RAG Pipeline" in parsed.metadata.get("headings", [])
    assert parsed.metadata.get("title") == "JakeAI Architecture"
    assert "enterprise platform" in parsed.content
    assert parsed.mime_type == "text/markdown"


def test_markdown_parser_heading_extraction_import_error() -> None:
    """Verify MarkdownParser continues parsing when markdown_it dependency is missing."""
    parser = MarkdownParser()
    md_content = "# Section 1\n\nSome body text here.\n\n## Section 2\n\nMore details."

    with patch.dict("sys.modules", {"markdown_it": None}):
        parsed = parser.parse_text(
            md_content, filename="arch.md", metadata={"custom_tag": "preserved"}
        )

    # Document parsing succeeds
    assert "Some body text here." in parsed.content
    assert parsed.mime_type == "text/markdown"
    # Optional headings become empty
    assert parsed.metadata.get("headings", []) == []
    assert "title" not in parsed.metadata
    # Unrelated metadata is preserved intact
    assert parsed.metadata.get("custom_tag") == "preserved"
    assert parsed.metadata.get("byte_size") == len(md_content.encode("utf-8"))
    assert parsed.metadata.get("char_count") == len(parsed.content)


def test_markdown_parser_heading_extraction_parser_error() -> None:
    """Verify MarkdownParser handles expected parser errors (ValueError, TypeError) gracefully."""
    parser = MarkdownParser()
    md_content = "# Heading Title\n\nContent paragraph."

    with patch(
        "markdown_it.MarkdownIt.parse", side_effect=ValueError("Corrupt token tree")
    ):
        parsed = parser.parse_text(
            md_content, filename="corrupt.md", metadata={"tenant_id": "tenant-test"}
        )

    # Parsing still completes without headings
    assert "Content paragraph." in parsed.content
    assert parsed.metadata.get("headings", []) == []
    assert parsed.metadata.get("tenant_id") == "tenant-test"


def test_markdown_parser_unexpected_exception_propagates() -> None:
    """Verify unexpected programming errors (RuntimeError, KeyError) are not silently swallowed."""
    parser = MarkdownParser()
    md_content = "# Critical Heading\n\nDocument body."

    with (
        patch(
            "markdown_it.MarkdownIt.parse",
            side_effect=RuntimeError("Unexpected fatal bug"),
        ),
        pytest.raises(RuntimeError, match="Unexpected fatal bug"),
    ):
        parser.parse_text(md_content, filename="critical.md")


def test_pdf_parser_text_and_pages() -> None:
    """Verify PDFParser extracts text and page metadata using pypdf."""
    import pypdf

    # Create an in-memory PDF using pypdf Writer
    writer = pypdf.PdfWriter()
    # Add page with blank stream (or minimal PDF structure)
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    parser = PDFParser()
    assert ".pdf" in parser.supported_extensions
    assert "application/pdf" in parser.supported_mime_types

    parsed = parser.parse_bytes(pdf_bytes, filename="report.pdf")
    assert parsed.mime_type == "application/pdf"
    assert parsed.metadata["total_pages"] == 1
    assert "pages" in parsed.metadata


def test_get_parser_resolution_and_rejection() -> None:
    """Verify get_parser resolves valid types and rejects unsupported formats."""
    # Valid extensions
    assert isinstance(get_parser("doc.txt"), PlainTextParser)
    assert isinstance(get_parser("readme.md"), MarkdownParser)
    assert isinstance(get_parser("statement.pdf"), PDFParser)

    # Valid MIME types
    assert isinstance(get_parser(mime_type="text/plain"), PlainTextParser)
    assert isinstance(get_parser(mime_type="text/markdown"), MarkdownParser)
    assert isinstance(get_parser(mime_type="application/pdf"), PDFParser)

    # Raw text without extension
    assert isinstance(get_parser("Dividend Notice", is_raw_text=True), PlainTextParser)

    # Unsupported format rejection
    with pytest.raises(UnsupportedDocumentTypeError):
        get_parser("malicious.exe")

    with pytest.raises(UnsupportedDocumentTypeError):
        get_parser("archive.zip")

    with pytest.raises(UnsupportedDocumentTypeError):
        get_parser("photo.png")


@pytest.mark.asyncio
async def test_ingest_file_bytes_markdown_and_pdf() -> None:
    """Verify DocumentIngestionPipeline.ingest_file_bytes parses markdown and pdf bytes."""
    from app.rag.ingestion import default_ingestion_pipeline

    md_data = b"# Section Header\n\nSome important technical documentation content."
    res = await default_ingestion_pipeline.ingest_file_bytes(
        data=md_data,
        filename="guide.md",
        tenant_id="tenant-file-bytes",
    )
    assert res.status == "success"
    assert res.indexed_chunks >= 1
    assert res.tenant_id == "tenant-file-bytes"
