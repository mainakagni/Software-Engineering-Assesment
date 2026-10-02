"""
Text Chunker — Recursive Character Splitter
Splits text into overlapping chunks suitable for embedding.

Strategy: recursive splitting on paragraph → sentence → word boundaries,
keeping chunks at ~512 tokens (≈ 2048 chars) with 50-token overlap (≈ 200 chars).
This balances retrieval precision (smaller chunks = more targeted) with
context (overlap ensures sentences near boundaries aren't split mid-thought).
"""
from __future__ import annotations
from typing import List


def split_text(
    text: str,
    chunk_size: int = 2048,   # characters (~512 tokens for most English text)
    chunk_overlap: int = 200,  # characters
) -> List[str]:
    """
    Recursively split text on paragraph, sentence, then character boundaries.
    Returns a list of non-empty string chunks.
    """
    if not text or not text.strip():
        return []

    separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]

    def _split(text: str, sep_idx: int) -> List[str]:
        if len(text) <= chunk_size or sep_idx >= len(separators):
            return [text.strip()] if text.strip() else []

        sep = separators[sep_idx]
        parts = text.split(sep) if sep else list(text)
        chunks: List[str] = []
        current = ""

        for part in parts:
            candidate = (current + sep + part) if current else part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    chunks.extend(_split(current, sep_idx + 1))
                current = part

        if current:
            chunks.extend(_split(current, sep_idx + 1))
        return chunks

    raw_chunks = _split(text, 0)

    # Apply overlap: each chunk includes the tail of the previous chunk
    effective_overlap = min(chunk_overlap, max(0, chunk_size // 4))
    if effective_overlap <= 0 or len(raw_chunks) <= 1:
        return raw_chunks

    overlapped: List[str] = [raw_chunks[0]]
    for i in range(1, len(raw_chunks)):
        tail = raw_chunks[i - 1][-effective_overlap:]
        overlapped.append(tail + " " + raw_chunks[i])

    return [c.strip() for c in overlapped if c.strip()]
