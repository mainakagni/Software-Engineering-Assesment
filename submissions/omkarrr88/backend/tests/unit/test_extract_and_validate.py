import io

import pytest

from app.documents.validation import clean_filename, read_limited, validate_upload
from app.errors import PayloadTooLargeError, UnsupportedMediaTypeError, ValidationFailedError
from app.ingestion.extract import ExtractionError, clean_text, extract_pdf, extract_plain
from tests.pdf_factory import make_encrypted_pdf, make_pdf

# --- upload validation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "data", "kind", "content_type"),
    [
        ("Policy.PDF", make_pdf(["hello"]), "pdf", "application/pdf"),
        ("notes.txt", b"plain text", "text", "text/plain"),
        ("guide.md", "# Title\ncaf\u00e9".encode(), "markdown", "text/markdown"),
        ("guide.markdown", b"\xef\xbb\xbfwith a BOM", "markdown", "text/markdown"),
    ],
)
def test_accepts_supported_files(filename: str, data: bytes, kind: str, content_type: str) -> None:
    upload = validate_upload(filename, data)
    assert (upload.kind, upload.content_type) == (kind, content_type)
    assert len(upload.sha256) == 64


@pytest.mark.parametrize(
    ("filename", "data", "error"),
    [
        ("report.docx", b"PK\x03\x04", UnsupportedMediaTypeError),
        ("no-extension", b"text", UnsupportedMediaTypeError),
        ("fake.pdf", b"just text", UnsupportedMediaTypeError),
        ("latin1.txt", "caf\u00e9".encode("latin-1"), UnsupportedMediaTypeError),
        ("binary.txt", b"abc\x00def", UnsupportedMediaTypeError),
        ("empty.txt", b"", ValidationFailedError),
        ("blank.md", b"  \n\n ", ValidationFailedError),
    ],
)
def test_rejects_bad_files(filename: str, data: bytes, error: type[Exception]) -> None:
    with pytest.raises(error):
        validate_upload(filename, data)


def test_read_limited_stops_at_the_limit() -> None:
    assert read_limited(io.BytesIO(b"x" * 100), max_bytes=100) == b"x" * 100
    with pytest.raises(PayloadTooLargeError):
        read_limited(io.BytesIO(b"x" * 101), max_bytes=100)


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\me\\report.pdf", "report.pdf"),
        ("bad\x00name\x1b[31m.md", "badname[31m.md"),
        (None, ""),
    ],
)
def test_filenames_are_display_text_only(raw: str | None, cleaned: str) -> None:
    assert clean_filename(raw) == cleaned


def test_long_filenames_keep_their_extension() -> None:
    cleaned = clean_filename("a" * 500 + ".pdf")
    assert len(cleaned) == 200
    assert cleaned.endswith(".pdf")


# --- extraction ---------------------------------------------------------------------------------


def test_clean_text_removes_control_characters_and_extra_space() -> None:
    raw = "Line\x00 one\r\nline   two\t\tend\x07\n\n\n\nNew  paragraph  "
    assert clean_text(raw) == "Line one\nline two end\n\nNew paragraph"


def test_plain_text_is_one_page_without_a_number() -> None:
    extracted = extract_plain("\ufeffHello\r\nworld".encode())
    assert extracted.page_count is None
    assert [(p.page, p.text) for p in extracted.pages] == [(None, "Hello\nworld")]


def test_pdf_pages_keep_their_numbers_and_blank_pages_are_skipped() -> None:
    extracted = extract_pdf(make_pdf(["First page.", "", "Third page."]), max_pages=10)
    assert extracted.page_count == 3
    assert [(p.page, p.text) for p in extracted.pages] == [(1, "First page."), (3, "Third page.")]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (make_encrypted_pdf("secret"), "password-protected"),
        (make_pdf(["", ""]), "Scanned PDFs are not supported"),
        (b"%PDF-1.7 and then nothing useful", "could not be read"),
        (make_pdf(["a", "b", "c"]), "more than 2 pages"),
    ],
    ids=["encrypted", "no-text", "corrupt", "too-many-pages"],
)
def test_unusable_pdfs_fail_with_a_readable_reason(data: bytes, message: str) -> None:
    with pytest.raises(ExtractionError, match=message):
        extract_pdf(data, max_pages=2)


def test_empty_text_file_fails() -> None:
    with pytest.raises(ExtractionError):
        extract_plain(b"\x00\x01  \n")
