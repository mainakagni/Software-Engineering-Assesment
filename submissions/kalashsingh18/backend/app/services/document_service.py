import os
import uuid
from typing import List
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from app.config import settings
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.services.celery_tasks import process_document_task

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}


def upload_document(db: Session, file: UploadFile, user_id: uuid.UUID) -> Document:

    filename = file.filename or "unknown.txt"
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type .{ext}. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_bytes = file.file.read()
    file_size = len(file_bytes)
    max_bytes = settings.MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024

    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_FILE_SIZE_MB}MB."
        )

    doc_id = uuid.uuid4()
    stored_filename = f"{doc_id}_{filename}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    document = Document(
        id=doc_id,
        user_id=user_id,
        filename=filename,
        file_type=ext,
        file_size=file_size,
        file_path=file_path,
        status="queued"
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        process_document_task.delay(str(doc_id))
    except Exception:
        process_document_task(str(doc_id))

    return document


def list_user_documents(db: Session, user_id: uuid.UUID) -> List[Document]:
    return (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
        .all()
    )


def get_user_document(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied."
        )
    return doc


def delete_user_document(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> None:
    
    doc = get_user_document(db, document_id, user_id)
    
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass

    db.delete(doc)
    db.commit()
