"""Resume text extraction — Phase 7.

Supports three input methods:
  1. PDF file → text via pdfplumber
  2. DOCX file → text via python-docx
  3. Raw text (pasted by user)

Normalisation: collapse whitespace, strip, enforce max length.
Error handling: unsupported format, empty/corrupt file, size exceeded.
"""

from __future__ import annotations

import io
import re
from typing import BinaryIO

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_TEXT_LENGTH = 50_000  # characters after extraction
SUPPORTED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}
SUPPORTED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ResumeParseError(Exception):
    """Raised when resume text cannot be extracted."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages_text: list[str] = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            if not pages_text:
                raise ResumeParseError(
                    "PDF-файл не содержит извлекаемого текста. "
                    "Возможно, это сканированный документ."
                )
            return "\n\n".join(pages_text)
    except ResumeParseError:
        raise
    except Exception as exc:
        logger.warning("pdf_parse_error", error=str(exc))
        raise ResumeParseError(
            "Не удалось прочитать PDF-файл. Файл повреждён или имеет неподдерживаемый формат."
        ) from exc


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    from docx import Document

    try:
        doc = Document(io.BytesIO(file_bytes))
        paragraphs: list[str] = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)
        if not paragraphs:
            raise ResumeParseError("DOCX-файл не содержит текста.")
        return "\n\n".join(paragraphs)
    except ResumeParseError:
        raise
    except Exception as exc:
        logger.warning("docx_parse_error", error=str(exc))
        raise ResumeParseError(
            "Не удалось прочитать DOCX-файл. Файл повреждён или имеет неподдерживаемый формат."
        ) from exc


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def normalise_text(raw_text: str) -> str:
    """Clean and truncate extracted resume text.

    - Collapse multiple whitespace/newlines
    - Strip leading/trailing whitespace
    - Enforce MAX_TEXT_LENGTH
    """
    # Replace \r\n with \n, collapse 3+ newlines into 2
    text = raw_text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces into one (preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = text.strip()

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        logger.info("resume_text_truncated", original_len=len(
            raw_text), truncated_to=MAX_TEXT_LENGTH)

    return text


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def detect_format(filename: str | None, content_type: str | None) -> str | None:
    """Detect resume format from filename extension or content type.

    Returns 'pdf', 'docx', or None if unknown.
    """
    if content_type and content_type in SUPPORTED_CONTENT_TYPES:
        return SUPPORTED_CONTENT_TYPES[content_type]
    if filename:
        for ext, fmt in SUPPORTED_EXTENSIONS.items():
            if filename.lower().endswith(ext):
                return fmt
    return None


def extract_text(
    *,
    file_bytes: bytes | None = None,
    filename: str | None = None,
    content_type: str | None = None,
    raw_text: str | None = None,
) -> str:
    """Extract and normalise resume text from file or raw input.

    Parameters
    ----------
    file_bytes : binary content of uploaded file (PDF or DOCX).
    filename : original filename (for format detection).
    content_type : MIME content type (for format detection).
    raw_text : plain text pasted by user.

    Returns
    -------
    Normalised resume text, ready for sanitisation and analysis.

    Raises
    ------
    ResumeParseError on validation/parsing failures (→ 4xx HTTP).
    """
    # --- Raw text path ---
    if raw_text is not None:
        text = raw_text.strip()
        if not text:
            raise ResumeParseError("Текст резюме не может быть пустым.")
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]
        return normalise_text(text)

    # --- File path ---
    if file_bytes is None:
        raise ResumeParseError(
            "Необходимо загрузить файл (PDF/DOCX) или вставить текст резюме."
        )

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ResumeParseError(
            f"Файл слишком большой. Максимальный размер: "
            f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} МБ.",
            status_code=413,
        )

    if len(file_bytes) == 0:
        raise ResumeParseError("Загруженный файл пуст.")

    fmt = detect_format(filename, content_type)
    if fmt is None:
        raise ResumeParseError(
            "Неподдерживаемый формат файла. Поддерживаются PDF и DOCX."
        )

    if fmt == "pdf":
        raw = extract_text_from_pdf(file_bytes)
    elif fmt == "docx":
        raw = extract_text_from_docx(file_bytes)
    else:
        raise ResumeParseError(f"Неподдерживаемый формат: {fmt}")

    return normalise_text(raw)
