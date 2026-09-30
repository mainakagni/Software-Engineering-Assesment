"""Text extraction. Failures here are permanent: retrying will not make a PDF readable."""

import io
import logging
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger(__name__)

# Control characters except tab and newline. NUL in particular cannot be stored in Postgres.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = re.compile("[ \t\u00a0]+")  # spaces, tabs, no-break spaces
_BLANK_LINES = re.compile(r"\n{3,}")


class ExtractionError(Exception):
    """The file cannot be turned into text. The message is shown to the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class PageText:
    page: int | None  # 1-based PDF page; None for text files
    text: str


@dataclass(frozen=True)
class ExtractedText:
    pages: list[PageText]
    page_count: int | None


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def extract_plain(data: bytes) -> ExtractedText:
    text = clean_text(data.decode("utf-8-sig", errors="replace"))
    if not text:
        raise ExtractionError("The file has no text in it.")
    return ExtractedText(pages=[PageText(page=None, text=text)], page_count=None)


def extract_pdf(data: bytes, *, max_pages: int) -> ExtractedText:
    reader = _open_pdf(data)
    try:
        page_count = len(reader.pages)
    except PyPdfError as exc:
        raise ExtractionError("The PDF could not be read. It may be damaged.") from exc
    if page_count > max_pages:
        raise ExtractionError(f"The PDF has more than {max_pages} pages.")

    pages: list[PageText] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = clean_text(page.extract_text() or "")
        except Exception:  # one bad page should not lose the whole document
            logger.warning("extract.page_failed", extra={"page": number}, exc_info=True)
            continue
        if text:
            pages.append(PageText(page=number, text=text))
    if not pages:
        raise ExtractionError("No text could be extracted. Scanned PDFs are not supported.")
    return ExtractedText(pages=pages, page_count=page_count)


def _open_pdf(data: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(data))
    except (PyPdfError, ValueError, KeyError, TypeError) as exc:
        raise ExtractionError("The PDF could not be read. It may be damaged.") from exc
    if reader.is_encrypted:
        # Some PDFs are encrypted with an empty password only to restrict editing; those open fine.
        try:
            opened = reader.decrypt("")
        except (PyPdfError, NotImplementedError) as exc:
            raise ExtractionError("The PDF is password-protected.") from exc
        if not opened:
            raise ExtractionError("The PDF is password-protected.")
    return reader
