"""Checks on uploaded files before anything is stored."""

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import BinaryIO, Literal

from app.errors import PayloadTooLargeError, UnsupportedMediaTypeError, ValidationFailedError

DocumentKind = Literal["pdf", "text", "markdown"]

# Extension -> (kind, the content type we store). The client's declared type is ignored: it is
# whatever the browser guessed, and the bytes are checked instead.
SUPPORTED_EXTENSIONS: dict[str, tuple[DocumentKind, str]] = {
    ".pdf": ("pdf", "application/pdf"),
    ".txt": ("text", "text/plain"),
    ".md": ("markdown", "text/markdown"),
    ".markdown": ("markdown", "text/markdown"),
}
KIND_BY_CONTENT_TYPE: dict[str, DocumentKind] = {
    content_type: kind for kind, content_type in SUPPORTED_EXTENSIONS.values()
}
MAX_FILENAME_LENGTH = 200
READ_BLOCK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    kind: DocumentKind
    content_type: str
    data: bytes
    sha256: str


def read_limited(stream: BinaryIO, max_bytes: int) -> bytes:
    """Reads the whole upload, failing as soon as it passes `max_bytes`."""
    blocks: list[bytes] = []
    total = 0
    while block := stream.read(READ_BLOCK_BYTES):
        total += len(block)
        if total > max_bytes:
            raise PayloadTooLargeError(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
        blocks.append(block)
    return b"".join(blocks)


def clean_filename(raw: str | None) -> str:
    """Display name only (never used as a path): last path segment, no control characters."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, extension = name.rpartition(".")
        if dot and 0 < len(extension) <= 10:  # keep the extension, shorten the stem
            name = f"{stem[: MAX_FILENAME_LENGTH - len(extension) - 1]}.{extension}"
        else:
            name = name[:MAX_FILENAME_LENGTH]
    return name


def validate_upload(raw_filename: str | None, data: bytes) -> ValidatedUpload:
    filename = clean_filename(raw_filename)
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedMediaTypeError("Only PDF, .txt and .md files are supported.")
    if not data:
        raise ValidationFailedError("The file is empty.")

    kind, content_type = SUPPORTED_EXTENSIONS[extension]
    if kind == "pdf":
        if not data.startswith(b"%PDF-"):
            raise UnsupportedMediaTypeError("This file does not look like a PDF.")
    else:
        _check_text(data)
    return ValidatedUpload(
        filename=filename,
        kind=kind,
        content_type=content_type,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _check_text(data: bytes) -> None:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedMediaTypeError("Text files must be UTF-8 encoded.") from exc
    if "\x00" in text:
        raise UnsupportedMediaTypeError("This file looks binary, not like text.")
    if not text.strip():
        raise ValidationFailedError("The file has no text in it.")
