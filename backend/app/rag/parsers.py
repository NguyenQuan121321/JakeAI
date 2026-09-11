"""Document parsers for plain text, Markdown, and PDF formats."""

from __future__ import annotations

import io
import logging
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.rag.normalizer import normalize_text

logger = logging.getLogger(__name__)


class UnsupportedDocumentTypeError(ValueError):
    """Raised when a file format or MIME type is not supported by the ingestion pipeline."""

    pass


class ParsedDocument(BaseModel):
    """Normalized output from a document parser containing extracted text and metadata."""

    content: str = Field(..., description="Normalized extracted document text")
    source: str = Field(..., description="Original filename, URI, or title")
    mime_type: str = Field(..., description="Validated MIME type")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Extracted structural document metadata"
    )


class BaseDocumentParser(ABC):
    """Abstract base contract for document format parsers."""

    @property
    @abstractmethod
    def supported_mime_types(self) -> set[str]:
        """Set of supported MIME types."""
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """Set of supported file extensions (including leading dot)."""
        pass

    @abstractmethod
    def parse_bytes(
        self,
        data: bytes,
        filename: str = "document",
        metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        """Parse raw binary data into a ParsedDocument."""
        pass

    def parse_text(
        self,
        text: str,
        filename: str = "document",
        metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        """Parse raw text into a ParsedDocument."""
        return self.parse_bytes(
            data=text.encode("utf-8"),
            filename=filename,
            metadata=metadata,
        )


class PlainTextParser(BaseDocumentParser):
    """Parser for raw plain text documents (.txt, text/plain)."""

    @property
    def supported_mime_types(self) -> set[str]:
        return {"text/plain", "text/csv", "application/json"}

    @property
    def supported_extensions(self) -> set[str]:
        return {".txt", ".text", ".log", ".csv", ".json"}

    def parse_bytes(
        self,
        data: bytes,
        filename: str = "document.txt",
        metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        meta = metadata.copy() if metadata else {}
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")

        normalized = normalize_text(text)
        meta["byte_size"] = len(data)
        meta["char_count"] = len(normalized)

        return ParsedDocument(
            content=normalized,
            source=filename,
            mime_type="text/plain",
            metadata=meta,
        )


class MarkdownParser(BaseDocumentParser):
    """Structure-aware Markdown parser extracting section headings and prose."""

    @property
    def supported_mime_types(self) -> set[str]:
        return {"text/markdown", "text/x-markdown"}

    @property
    def supported_extensions(self) -> set[str]:
        return {".md", ".markdown"}

    def parse_bytes(
        self,
        data: bytes,
        filename: str = "document.md",
        metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        meta = metadata.copy() if metadata else {}
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")

        headings: list[str] = []
        try:
            from markdown_it import MarkdownIt

            md = MarkdownIt()
            tokens = md.parse(text)
            for i, token in enumerate(tokens):
                if (
                    token.type == "heading_open"
                    and i + 1 < len(tokens)
                    and tokens[i + 1].type == "inline"
                ):
                    headings.append(tokens[i + 1].content)
        except (ImportError, ModuleNotFoundError) as exc:
            logger.warning(
                "Optional Markdown heading extraction unavailable: markdown_it dependency missing (%s). Continuing without headings.",
                type(exc).__name__,
            )
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning(
                "Optional Markdown heading extraction failed during token parsing (%s). Continuing without headings.",
                type(exc).__name__,
            )

        normalized = normalize_text(text)
        meta["byte_size"] = len(data)
        meta["char_count"] = len(normalized)
        if headings:
            meta["headings"] = headings
            if "title" not in meta:
                meta["title"] = headings[0]

        return ParsedDocument(
            content=normalized,
            source=filename,
            mime_type="text/markdown",
            metadata=meta,
        )


class PDFParser(BaseDocumentParser):
    """Page-aware PDF parser extracting text and page metadata using pypdf."""

    @property
    def supported_mime_types(self) -> set[str]:
        return {"application/pdf", "application/x-pdf"}

    @property
    def supported_extensions(self) -> set[str]:
        return {".pdf"}

    def parse_bytes(
        self,
        data: bytes,
        filename: str = "document.pdf",
        metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        meta = metadata.copy() if metadata else {}
        if not data.startswith(b"%PDF"):
            # Plain text string passed with a .pdf source filename (pre-extracted text)

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1", errors="replace")
            normalized = normalize_text(text)
            meta["byte_size"] = len(data)
            meta["char_count"] = len(normalized)
            meta["format_note"] = "pre-extracted text"
            return ParsedDocument(
                content=normalized,
                source=filename,
                mime_type="application/pdf",
                metadata=meta,
            )

        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(data))
        except Exception as exc:
            raise ValueError(f"Failed to read PDF file '{filename}': {exc}") from exc

        page_texts: list[str] = []
        pages_metadata: list[dict[str, Any]] = []

        for page_idx, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            norm_text = normalize_text(raw_text)
            if norm_text:
                page_texts.append(f"[Page {page_idx}]\n{norm_text}")
                pages_metadata.append(
                    {"page_number": page_idx, "char_count": len(norm_text)}
                )

        full_content = "\n\n".join(page_texts)
        meta["byte_size"] = len(data)
        meta["total_pages"] = len(reader.pages)
        meta["extracted_pages"] = len(pages_metadata)
        meta["pages"] = pages_metadata

        return ParsedDocument(
            content=full_content,
            source=filename,
            mime_type="application/pdf",
            metadata=meta,
        )


_PARSERS: list[BaseDocumentParser] = [
    PDFParser(),
    MarkdownParser(),
    PlainTextParser(),
]


def get_parser(
    filename: str = "document.txt",
    mime_type: str | None = None,
    is_raw_text: bool = False,
) -> BaseDocumentParser:
    """Resolve parser by file extension and MIME type, or raise UnsupportedDocumentTypeError."""
    ext = Path(filename).suffix.lower()
    guessed_mime = mime_type or mimetypes.guess_type(filename)[0]

    for parser in _PARSERS:
        if ext and ext in parser.supported_extensions:
            return parser
        if guessed_mime and guessed_mime in parser.supported_mime_types:
            return parser

    # If the input is raw text string and does not have an explicit unsupported file extension, treat as plain text
    unsupported_binary_extensions = {
        ".exe",
        ".bin",
        ".tar",
        ".gz",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".mp4",
        ".mp3",
        ".dll",
        ".so",
        ".dylib",
        ".iso",
        ".7z",
    }
    if is_raw_text and (not ext or ext not in unsupported_binary_extensions):
        return PlainTextParser()

    raise UnsupportedDocumentTypeError(
        f"Unsupported document format for file '{filename}' with MIME type '{guessed_mime}'. "
        f"Supported extensions: {', '.join(sorted({e for p in _PARSERS for e in p.supported_extensions}))}"
    )
