"""
Ingestion Task — Document processing pipeline
1. Extract text from PDF or plain text
2. Chunk text using recursive splitter
3. Embed chunks using Gemini
4. Store chunks + embeddings in PostgreSQL (pgvector)
5. Update document status
"""
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import execute_values

from worker import app

logger = logging.getLogger(__name__)

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "2048"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))


def get_sync_conn():
    """Get a synchronous psycopg2 connection."""
    url = os.getenv("DATABASE_URL", "postgresql://documind:changeme@postgres:5432/documind")
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    return psycopg2.connect(url)


def update_doc_status(doc_id: str, status: str, error: str = None, chunk_count: int = None):
    conn = get_sync_conn()
    status_val = status.upper() if isinstance(status, str) else status.name.upper()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM documents WHERE id=%s", (doc_id,))
                if not cur.fetchone():
                    return
                now = datetime.now(timezone.utc)
                if status_val in ("READY", "FAILED"):
                    cur.execute(
                        """UPDATE documents SET status=%s, error_message=%s, chunk_count=%s, processed_at=%s
                           WHERE id=%s""",
                        (status_val, error, chunk_count, now, doc_id),
                    )
                else:
                    cur.execute("UPDATE documents SET status=%s WHERE id=%s", (status_val, doc_id))
    except Exception as exc:
        logger.warning(f"Failed to update document status for {doc_id}: {exc}")
    finally:
        conn.close()


def extract_text_pdf(file_path: str) -> List[tuple]:
    """Extract text from PDF, returning list of (page_number, text) tuples."""
    try:
        import pymupdf  # PyMuPDF
        doc = pymupdf.open(file_path)
        pages = []
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            if text.strip():
                pages.append((page_num, text))
        doc.close()
        return pages
    except Exception as exc:
        logger.error(f"PDF extraction failed: {exc}")
        raise


def extract_text_plain(file_path: str) -> List[tuple]:
    """Extract text from plain text or Markdown file."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return [(None, f.read())]


def chunk_text(text: str) -> List[str]:
    """Split text using recursive character splitter."""
    separators = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]

    def _split(t: str, sep_idx: int) -> List[str]:
        if len(t) <= CHUNK_SIZE or sep_idx >= len(separators):
            return [t.strip()] if t.strip() else []
        sep = separators[sep_idx]
        parts = t.split(sep) if sep else list(t)
        chunks, current = [], ""
        for part in parts:
            candidate = (current + sep + part) if current else part
            if len(candidate) <= CHUNK_SIZE:
                current = candidate
            else:
                if current:
                    chunks.extend(_split(current, sep_idx + 1))
                current = part
        if current:
            chunks.extend(_split(current, sep_idx + 1))
        return chunks

    raw = _split(text, 0)
    effective_overlap = min(CHUNK_OVERLAP, max(0, CHUNK_SIZE // 4))
    if effective_overlap <= 0 or len(raw) <= 1:
        return raw
    result = [raw[0]]
    for i in range(1, len(raw)):
        tail = raw[i - 1][-effective_overlap:]
        result.append(tail + " " + raw[i])
    return [c.strip() for c in result if c.strip()]


def embed_chunks(texts: List[str]) -> List[List[float]]:
    """Embed text chunks using Gemini embedding model."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing or empty")

    from google import genai
    from google.genai.types import EmbedContentConfig

    client = genai.Client(api_key=api_key)

    BATCH_SIZE = 100
    all_embeddings = []
    model = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        config = EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        try:
            result = client.models.embed_content(
                model=model,
                contents=batch,
                config=config,
            )
        except Exception as exc:
            if "404" in str(exc) or "NOT_FOUND" in str(exc) or "not found" in str(exc).lower():
                logger.info(f"Primary embedding model '{model}' not found, falling back to 'gemini-embedding-001'")
                fb_config = EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=768,
                )
                result = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=batch,
                    config=fb_config,
                )
            else:
                raise
        all_embeddings.extend([e.values for e in result.embeddings])

    return all_embeddings


def store_chunks(doc_id: str, owner_id: str, chunks_data: List[dict]):
    """Bulk-insert chunks with embeddings into PostgreSQL."""
    conn = get_sync_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM documents WHERE id=%s", (doc_id,))
                if not cur.fetchone():
                    logger.info(f"Document {doc_id} no longer exists, skipping chunk storage")
                    return
                now = datetime.now(timezone.utc)
                rows = [
                    (
                        str(uuid.uuid4()),
                        doc_id,
                        owner_id,
                        c["chunk_index"],
                        c["content"],
                        c.get("page_number"),
                        "[" + ",".join(str(v) for v in c["embedding"]) + "]",
                        "{}",
                        now,
                    )
                    for c in chunks_data
                ]
                execute_values(
                    cur,
                    """INSERT INTO document_chunks
                       (id, document_id, owner_id, chunk_index, content, page_number, embedding, metadata, created_at)
                       VALUES %s""",
                    rows,
                )
    except psycopg2.errors.ForeignKeyViolation:
        logger.info(f"Document {doc_id} was deleted during chunk storage")
    finally:
        conn.close()


def process_document_ingestion(doc_id: str, file_path: str, owner_id: str, mime_type: str):
    """
    Core document ingestion pipeline:
    extract → chunk → embed → store → update status
    Can be called directly, via FastAPI BackgroundTasks, or from Celery worker.
    """
    logger.info(f"[{doc_id}] Starting ingestion", extra={"doc_id": doc_id, "mime_type": mime_type})

    try:
        update_doc_status(doc_id, "PROCESSING")

        # Extract text
        if mime_type == "application/pdf":
            pages = extract_text_pdf(file_path)
        else:
            pages = extract_text_plain(file_path)

        # Chunk each page
        all_chunks = []
        chunk_idx = 0
        for page_num, text in pages:
            for chunk_text_str in chunk_text(text):
                all_chunks.append({
                    "chunk_index": chunk_idx,
                    "content": chunk_text_str,
                    "page_number": page_num,
                })
                chunk_idx += 1

        if not all_chunks:
            raise ValueError("No text could be extracted from document")

        logger.info(f"[{doc_id}] Created {len(all_chunks)} chunks")

        # Embed chunks
        texts = [c["content"] for c in all_chunks]
        embeddings = embed_chunks(texts)

        for i, emb in enumerate(embeddings):
            all_chunks[i]["embedding"] = emb

        # Store in DB
        store_chunks(doc_id, owner_id, all_chunks)

        # Mark ready
        update_doc_status(doc_id, "READY", chunk_count=len(all_chunks))
        logger.info(f"[{doc_id}] Ingestion complete: {len(all_chunks)} chunks stored")

        return {"doc_id": doc_id, "chunks": len(all_chunks)}

    except psycopg2.errors.ForeignKeyViolation:
        logger.info(f"[{doc_id}] Document was deleted during ingestion; stopping gracefully.")
    except Exception as exc:
        logger.exception(f"[{doc_id}] Ingestion failed: {exc}")
        try:
            update_doc_status(doc_id, "FAILED", error=str(exc)[:500])
        except Exception:
            pass
        raise


@app.task(
    name="worker.tasks.ingest_document",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def ingest_document(self, doc_id: str, file_path: str, owner_id: str, mime_type: str):
    """
    Celery task wrapper around core ingestion pipeline.
    """
    try:
        return process_document_ingestion(doc_id, file_path, owner_id, mime_type)
    except Exception as exc:
        raise self.retry(exc=exc)
