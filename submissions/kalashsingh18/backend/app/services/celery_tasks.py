import uuid
import logging
import os
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.rag.chunker import extract_text_from_pdf, extract_text_from_plain, chunk_text
from app.utils.embeddings import get_embedding

logger = logging.getLogger("documind.worker")


@celery_app.task(name="process_document_task", bind=True, max_retries=2)
def process_document_task(self, document_id_str: str):
    db = SessionLocal()
    doc_id = uuid.UUID(document_id_str)
    
    try:
        document = db.query(Document).filter(Document.id == doc_id).first()
        if not document:
            logger.error(f"Document {document_id_str} not found for background ingestion.")
            return

        document.status = "processing"
        document.error_message = None
        db.commit()

        if not document.file_path or not os.path.exists(document.file_path):
            raise FileNotFoundError(f"File payload missing at {document.file_path}")

        with open(document.file_path, "rb") as f:
            file_bytes = f.read()

        ext = document.filename.split(".")[-1].lower()
        if ext == "pdf":
            pages = extract_text_from_pdf(file_bytes)
        else:
            pages = extract_text_from_plain(file_bytes)

        chunks = chunk_text(pages, chunk_size=500, chunk_overlap=100)
        if not chunks:
            raise ValueError("No readable text found in document.")

        db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
        db.flush()

        BATCH_SIZE = 50
        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[batch_start: batch_start + BATCH_SIZE]
            for item in batch:
                vector = get_embedding(item["content"])
                chunk_record = DocumentChunk(
                    document_id=doc_id,
                    user_id=document.user_id,
                    chunk_index=item["chunk_index"],
                    page_number=item["page_number"],
                    content=item["content"],
                    embedding=vector,
                )
                db.add(chunk_record)
            db.flush()  
        document.status = "ready"
        db.commit()
        logger.info(f"Successfully processed document {document.filename} ({len(chunks)} chunks).")

    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to process document {document_id_str}: {exc}", exc_info=True)
        try:
            document = db.query(Document).filter(Document.id == doc_id).first()
            if document:
                document.status = "failed"
                document.error_message = str(exc)[:500]
                db.commit()
        except Exception:
            pass
        raise exc
    finally:
        db.close()
