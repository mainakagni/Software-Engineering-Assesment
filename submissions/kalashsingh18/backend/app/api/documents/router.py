import uuid
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.chunk import DocumentChunk
from app.utils.security import get_current_user
from app.services.document_service import (
    upload_document,
    list_user_documents,
    get_user_document,
    delete_user_document
)
from app.api.documents.schemas import DocumentResponse, DocumentDetailResponse

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
def upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return upload_document(db, file, current_user.id)


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return list_user_documents(db, current_user.id)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = get_user_document(db, document_id, current_user.id)
    chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count()
    return DocumentDetailResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        chunk_count=chunk_count
    )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    delete_user_document(db, document_id, current_user.id)
    return {"message": "Document and all vector embeddings deleted successfully."}


@router.post("/search")
def semantic_search(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.utils.embeddings import get_query_embedding
    from app.rag.vector_store import search_similar_chunks

    query_text = data.get("query", "").strip()
    if not query_text or len(query_text) < 2:
        return {"results": []}

    query_vec = get_query_embedding(query_text)
    results = search_similar_chunks(
        db=db,
        user_id=current_user.id,
        query_vector=query_vec,
        top_k=8
    )

    search_results = []
    query_words = set(w.lower() for w in query_text.split() if len(w) > 2)
    for chunk in results:
        content = chunk["content"]
        content_lower = content.lower()
        matched_words = [w for w in query_words if w in content_lower]
        relevance = len(matched_words) / max(len(query_words), 1)

        search_results.append({
            "document_id": str(chunk["document_id"]),
            "document_name": chunk["document_name"],
            "page_number": chunk["page_number"],
            "passage": content[:400],
            "relevance_score": round(relevance, 2),
            "matched_keywords": matched_words
        })

    return {"results": search_results, "total": len(search_results)}

