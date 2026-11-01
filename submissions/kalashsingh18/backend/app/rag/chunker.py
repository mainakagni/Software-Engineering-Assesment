import io
import re
from typing import List, Dict, Any
from pypdf import PdfReader


def extract_text_from_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    pages_data = []
    reader = PdfReader(io.BytesIO(file_bytes))
    for idx, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        # Normalise whitespace but preserve paragraph breaks
        page_text = re.sub(r"[ \t]+", " ", page_text)  # collapse horizontal whitespace
        page_text = re.sub(r"\n{3,}", "\n\n", page_text)  # collapse excessive blank lines
        cleaned = page_text.strip()
        if cleaned:
            pages_data.append({
                "page_number": idx + 1,
                "text": cleaned
            })
    return pages_data


def extract_text_from_plain(file_bytes: bytes) -> List[Dict[str, Any]]:
   
    try:
        content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = file_bytes.decode("latin-1", errors="replace")

    content = content.strip()
    if not content:
        return []

    raw_pages = re.split(r"\n\s*---\s*\n", content)
    if len(raw_pages) > 1:
        return [
            {"page_number": i + 1, "text": p.strip()}
            for i, p in enumerate(raw_pages)
            if p.strip()
        ]

    PAGE_CHAR_LIMIT = 3000
    pages_data = []
    page_num = 1
    current_page_chars = 0
    current_page_paragraphs: List[str] = []

    paragraphs = re.split(r"\n\n+", content)
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_page_chars > 0 and current_page_chars + len(para) > PAGE_CHAR_LIMIT:
            pages_data.append({
                "page_number": page_num,
                "text": "\n\n".join(current_page_paragraphs)
            })
            page_num += 1
            current_page_chars = 0
            current_page_paragraphs = []
        current_page_paragraphs.append(para)
        current_page_chars += len(para)

    if current_page_paragraphs:
        pages_data.append({
            "page_number": page_num,
            "text": "\n\n".join(current_page_paragraphs)
        })

    return pages_data


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_into_sentences(text: str) -> List[str]:
    sentences = _SENTENCE_SPLIT.split(text)
    result = []
    for s in sentences:
        s = s.strip()
        if s:
            result.append(s)
    return result


def chunk_text(
    pages: List[Dict[str, Any]],
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> List[Dict[str, Any]]:
  
    chunks: List[Dict[str, Any]] = []
    global_idx = 0

    for page_info in pages:
        page_num = page_info["page_number"]
        text = page_info["text"]

        if not text:
            continue

        sentences = _split_into_sentences(text)
        if not sentences:
            continue

        current_sentences: List[str] = []
        current_len = 0
        char_start = 0

        for sent in sentences:
            sent_len = len(sent) + 1  # +1 for the space separator

            if current_len + sent_len > chunk_size and current_sentences:
                # Emit the current chunk
                chunk_text_str = " ".join(current_sentences).strip()
                if chunk_text_str:
                    chunks.append({
                        "chunk_index": global_idx,
                        "page_number": page_num,
                        "content": chunk_text_str,
                        "char_start": char_start,
                    })
                    global_idx += 1

    
                overlap_budget = chunk_overlap
                overlap_sentences: List[str] = []
                for s in reversed(current_sentences):
                    if overlap_budget - len(s) - 1 >= 0:
                        overlap_sentences.insert(0, s)
                        overlap_budget -= len(s) + 1
                    else:
                        break

                char_start += current_len - sum(len(s) + 1 for s in overlap_sentences)
                current_sentences = overlap_sentences
                current_len = sum(len(s) + 1 for s in current_sentences)

            current_sentences.append(sent)
            current_len += sent_len

        if current_sentences:
            chunk_text_str = " ".join(current_sentences).strip()
            if chunk_text_str:
                chunks.append({
                    "chunk_index": global_idx,
                    "page_number": page_num,
                    "content": chunk_text_str,
                    "char_start": char_start,
                })
                global_idx += 1

    return chunks
