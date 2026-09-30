"""Splitting extracted text into chunks for embedding and citation.

Structure first (Markdown sections, then paragraphs), then sentences, then words for anything still
too long. The pieces are packed greedily into chunks of up to `size` characters. Each new chunk in
the same section starts with the last sentences of the previous one (up to `overlap` characters), so
a rule that straddles a boundary is still whole in one of them. Chunks never mix sections, so a
citation's section is always accurate.
"""

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from app.ingestion.extract import PageText

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
PARAGRAPH_BREAK = "\n\n"


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None


@dataclass(frozen=True)
class _Piece:
    text: str
    page: int | None
    section: str | None
    new_paragraph: bool


def embedding_text(chunk: Chunk) -> str:
    """What gets embedded: the section path gives short chunks their topic."""
    return f"{chunk.section}\n\n{chunk.text}" if chunk.section else chunk.text


def chunk_document(
    pages: Sequence[PageText], *, markdown: bool, size: int, overlap: int
) -> list[Chunk]:
    if size < 100 or not 0 <= overlap < size // 2:
        raise ValueError("chunk size must be >= 100 and overlap < size / 2")
    pieces = [
        piece
        for section, page, paragraph in _paragraphs(pages, markdown)
        for piece in _split_paragraph(paragraph, page, section, size)
    ]
    return _pack(pieces, size, overlap)


def _paragraphs(
    pages: Sequence[PageText], markdown: bool
) -> Iterator[tuple[str | None, int | None, str]]:
    headings: list[str] = []
    for page in pages:
        lines: list[str] = []
        in_fence = False
        for line in [*page.text.split("\n"), ""]:
            if markdown and _FENCE.match(line):
                in_fence = not in_fence
            heading = _HEADING.match(line) if markdown and not in_fence else None
            if heading or (not line.strip() and not in_fence):
                if lines:
                    yield _section(headings), page.page, _join_lines(lines, markdown)
                    lines = []
                if heading:
                    level = len(heading.group(1))
                    headings = [*headings[: level - 1], heading.group(2).strip()]
                continue
            lines.append(line)


def _section(headings: list[str]) -> str | None:
    return " > ".join(headings) if headings else None


def _join_lines(lines: list[str], markdown: bool) -> str:
    # Markdown lines carry structure (lists, tables); line breaks inside a PDF paragraph are just
    # where the page layout wrapped the text.
    return "\n".join(lines).strip() if markdown else " ".join(line.strip() for line in lines)


def _split_paragraph(text: str, page: int | None, section: str | None, size: int) -> list[_Piece]:
    parts = [text] if len(text) <= size else _split_long(text, size)
    return [
        _Piece(text=part, page=page, section=section, new_paragraph=(i == 0))
        for i, part in enumerate(parts)
    ]


def _split_long(text: str, size: int) -> list[str]:
    parts: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        if len(sentence) <= size:
            parts.append(sentence)
        else:
            parts.extend(_split_words(sentence, size))
    return [part for part in parts if part.strip()]


def _split_words(text: str, size: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > size:  # a single "word" longer than a chunk (e.g. a long URL)
            if current:
                parts.append(current)
                current = ""
            parts.append(word[:size])
            word = word[size:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= size:
            current = candidate
        else:
            parts.append(current)
            current = word
    if current:
        parts.append(current)
    return parts


def _pack(pieces: list[_Piece], size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    current: list[_Piece] = []
    for piece in pieces:
        if current and piece.section != current[-1].section:
            chunks.append(_make_chunk(len(chunks), current))
            current = []
        if current and len(_text(current)) + len(_separator(piece)) + len(piece.text) > size:
            chunks.append(_make_chunk(len(chunks), current))
            current = _overlap_tail(current, overlap, size - len(piece.text) - 1)
        current = [*current, piece]
    if current:
        chunks.append(_make_chunk(len(chunks), current))
    return chunks


def _overlap_tail(previous: list[_Piece], overlap: int, room: int) -> list[_Piece]:
    """The last sentences of the previous chunk that fit in `overlap` (and in the room left)."""
    budget = min(overlap, room)
    last = previous[-1]
    sentences = _SENTENCE_END.split(_text(previous))
    tail: list[str] = []
    for sentence in reversed(sentences):
        if len(" ".join([sentence, *tail])) > budget:
            break
        tail.insert(0, sentence)
    if not tail:
        return []
    return [_Piece(text=" ".join(tail), page=last.page, section=last.section, new_paragraph=True)]


def _separator(piece: _Piece) -> str:
    return PARAGRAPH_BREAK if piece.new_paragraph else " "


def _text(pieces: list[_Piece]) -> str:
    text = pieces[0].text
    for piece in pieces[1:]:
        text += _separator(piece) + piece.text
    return text


def _make_chunk(index: int, pieces: list[_Piece]) -> Chunk:
    pages = [piece.page for piece in pieces if piece.page is not None]
    return Chunk(
        index=index,
        text=_text(pieces),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        section=pieces[0].section,
    )
