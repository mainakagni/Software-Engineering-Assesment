"""Small, valid PDFs built in memory, so tests need no binary fixtures."""

import io

from pypdf import PdfReader, PdfWriter

LINE_WIDTH = 90


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            if line and len(line) + 1 + len(word) > LINE_WIDTH:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        lines.append(line)
    return lines


def _content_stream(text: str) -> bytes:
    if not text:
        return b""
    shown = " T* ".join(f"({_escape(line)}) Tj" for line in _wrap(text))
    return f"BT /F1 11 Tf 14 TL 72 740 Td {shown} ET".encode("latin-1")


def make_pdf(pages: list[str]) -> bytes:
    """A PDF with one page per string (Helvetica, wrapped lines). Empty strings give blank pages."""
    first_page = 4
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids = []
    for i, text in enumerate(pages):
        page_number, content_number = first_page + 2 * i, first_page + 2 * i + 1
        kids.append(f"{page_number} 0 R")
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
        ).encode()
        stream = _content_stream(text)
        objects[content_number] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = out.tell()
        out.write(f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n")
    xref_at = out.tell()
    size = max(objects) + 1
    out.write(f"xref\n0 {size}\n0000000000 65535 f \n".encode())
    for number in range(1, size):
        out.write(f"{offsets[number]:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode())
    return out.getvalue()


def make_encrypted_pdf(text: str, password: str = "secret") -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf([text]))))
    writer.encrypt(user_password=password, owner_password=password, algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
