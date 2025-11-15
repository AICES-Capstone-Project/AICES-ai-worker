"""Utilities for reading text content from resume files."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import logging

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".rtf"}


class UnsupportedFileTypeError(ValueError):
    """Raised when a file with an unsupported extension is provided."""


def extract_text_from_file(file_path: Union[str, Path]) -> str:
    """Extract plain text from a resume file.

    Args:
        file_path: Path to the resume file.

    Returns:
        Extracted plain-text resume content.

    Raises:
        FileNotFoundError: If the path does not exist.
        UnsupportedFileTypeError: If the file extension is not supported.
        RuntimeError: If an installed dependency is missing.
    """

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported resume format: {extension}")

    if extension == ".pdf":
        return _extract_from_pdf(path)
    if extension == ".docx":
        return _extract_from_docx(path)
    if extension == ".doc":
        return _extract_from_doc(path)
    return _extract_from_text_file(path)


def _extract_from_pdf(path: Path) -> str:
    try:
        import PyPDF2
    except ImportError as exc:
        raise RuntimeError(
            "PyPDF2 is required to extract PDF resumes") from exc

    text_chunks: list[str] = []
    with path.open("rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            try:
                text_chunks.append(page.extract_text() or "")
            except Exception as exc:  # pragma: no cover - PyPDF2 internals
                logger.debug(
                    "Skipping PDF page due to extraction error: %s", exc)
    return "\n".join(chunk.strip() for chunk in text_chunks).strip()


def _extract_from_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required to extract DOCX resumes") from exc

    doc = Document(str(path))
    return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()


def _extract_from_doc(path: Path) -> str:
    try:
        import docx2txt
    except ImportError as exc:
        raise RuntimeError(
            "docx2txt is required to extract legacy DOC resumes") from exc

    return docx2txt.process(str(path)).strip()


def _extract_from_text_file(path: Path) -> str:
    encodings = ("utf-8", "latin-1")
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding).strip()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "utf-8", b"", 0, 1, "Unable to decode text resume")
