"""Text extraction for uploaded screenplay/script files."""
from pathlib import Path
import fitz
import docx


class UnsupportedFormatError(Exception):
    pass


def extract_text(file_path: str, original_filename: str) -> str:
    suffix = Path(original_filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_path)
    if suffix == ".docx":
        return _extract_docx(file_path)
    if suffix in (".txt", ".fountain"):
        return _extract_plain(file_path)
    raise UnsupportedFormatError(
        f"'{suffix}' isn't supported yet. Upload a .pdf, .docx, .txt, or .fountain file."
    )


def _extract_pdf(file_path: str) -> str:
    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text("text"))
    return "\n".join(text_parts)


def _extract_docx(file_path: str) -> str:
    document = docx.Document(file_path)
    return "\n".join(p.text for p in document.paragraphs)


def _extract_plain(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
