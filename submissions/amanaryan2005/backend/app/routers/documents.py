"""
Documents Router — upload, list, get, delete
POST   /api/v1/documents         Upload a document
GET    /api/v1/documents         List user's documents
GET    /api/v1/documents/{id}    Get document status
DELETE /api/v1/documents/{id}    Delete document + embeddings
"""
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Document, DocumentStatus, DocumentChunk, User
from app.schemas import DocumentResponse, DocumentListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/documind_uploads")
ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/x-markdown": "md",
}

# Module-level Celery app for dispatching tasks (avoids creating per-request)
from celery import Celery as _Celery
_celery_app = _Celery(broker=settings.celery_broker_url)


def is_celery_worker_available() -> bool:
    """Check if at least one Celery worker is active to process tasks."""
    try:
        insp = _celery_app.control.inspect(timeout=0.5)
        ping_res = insp.ping()
        return bool(ping_res)
    except Exception:
        return False


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF, TXT, or Markdown document.
    Returns immediately; processing happens in Celery or FastAPI background task.
    """
    # Validate size
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb} MB.",
        )

    # Validate MIME type
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        # Also try extension
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in settings.allowed_extensions:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type '{mime_type}'. Allowed: PDF, TXT, MD.",
            )
        # Fix MIME type from extension
        mime_type = {"pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown"}.get(ext, mime_type)

    # Save file to disk
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    doc_id = uuid.uuid4()
    safe_filename = f"{doc_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # Create DB record
    doc = Document(
        id=doc_id,
        owner_id=current_user.id,
        filename=safe_filename,
        original_filename=file.filename or "unknown",
        file_size=len(content),
        mime_type=mime_type,
        status=DocumentStatus.QUEUED,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Dispatch ingestion task to Celery if available, or fallback to BackgroundTasks
    task_dispatched = False
    if is_celery_worker_available():
        try:
            task = _celery_app.send_task(
                "worker.tasks.ingest_document",
                args=[str(doc.id), file_path, str(current_user.id), mime_type],
            )
            doc.celery_task_id = task.id
            await db.commit()
            task_dispatched = True
        except Exception as exc:
            logger.warning(f"Could not dispatch Celery task: {exc}")

    if not task_dispatched:
        logger.info(f"Processing document {doc.id} via background task fallback")
        from worker.tasks import process_document_ingestion
        background_tasks.add_task(
            process_document_ingestion,
            str(doc.id), file_path, str(current_user.id), mime_type
        )

    logger.info(
        "Document uploaded",
        extra={"doc_id": str(doc.id), "upload_filename": file.filename, "user_id": str(current_user.id)},
    )
    return DocumentResponse.model_validate(doc)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    background_tasks: BackgroundTasks,
    status_filter: Optional[DocumentStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents belonging to the authenticated user."""
    query = select(Document).where(Document.owner_id == current_user.id).order_by(Document.created_at.desc())
    if status_filter:
        query = query.where(Document.status == status_filter)

    result = await db.execute(query)
    docs = result.scalars().all()

    # Trigger background ingestion for any queued documents if worker was missing
    for doc in docs:
        if doc.status == DocumentStatus.QUEUED:
            file_path = os.path.join(UPLOAD_DIR, doc.filename)
            if os.path.exists(file_path):
                from worker.tasks import process_document_ingestion
                background_tasks.add_task(
                    process_document_ingestion,
                    str(doc.id), file_path, str(doc.owner_id), doc.mime_type
                )

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document status and metadata."""
    doc = await db.get(Document, document_id)
    if not doc or doc.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status == DocumentStatus.QUEUED:
        file_path = os.path.join(UPLOAD_DIR, doc.filename)
        if os.path.exists(file_path):
            from worker.tasks import process_document_ingestion
            background_tasks.add_task(
                process_document_ingestion,
                str(doc.id), file_path, str(doc.owner_id), doc.mime_type
            )

    return DocumentResponse.model_validate(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and all its embeddings/chunks."""
    doc = await db.get(Document, document_id)
    if not doc or doc.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Cascade deletes chunks via FK
    await db.delete(doc)
    await db.commit()

    # Remove file from disk
    file_path = os.path.join(UPLOAD_DIR, doc.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    logger.info(
        "Document deleted",
        extra={"doc_id": str(document_id), "user_id": str(current_user.id)},
    )
