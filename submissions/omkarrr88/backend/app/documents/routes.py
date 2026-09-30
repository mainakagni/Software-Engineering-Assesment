import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile

from app.auth.deps import CurrentUser
from app.dependencies import DbSession, SettingsDep
from app.documents import service
from app.documents.schemas import DocumentOut
from app.documents.validation import read_limited, validate_upload
from app.envelope import Envelope, PageMeta, error_responses, ok
from app.logging_config import request_id_var

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post(
    "",
    status_code=202,
    response_model=Envelope[DocumentOut],
    responses=error_responses(401, 409, 411, 413, 415, 422),
)
def upload_document(
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="A PDF, .txt or .md file, up to 10 MB.")],
) -> Envelope[DocumentOut]:
    """Stores the file and queues it for processing. Poll the document until it is `ready`."""
    upload = validate_upload(file.filename, read_limited(file.file, settings.max_upload_bytes))
    document = service.create_document(
        session,
        user.id,
        upload,
        max_documents=settings.max_documents_per_user,
        request_id=request_id_var.get(),
    )
    logger.info(
        "document.uploaded",
        extra={
            "document_id": str(document.id),
            "content_type": document.content_type,
            "size_bytes": document.size_bytes,
        },
    )
    return ok(DocumentOut.model_validate(document))


@router.get("", response_model=Envelope[list[DocumentOut]], responses=error_responses(401, 422))
def list_documents(
    user: CurrentUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Envelope[list[DocumentOut]]:
    """Your documents, newest first."""
    documents, total = service.list_documents(session, user.id, limit=limit, offset=offset)
    return ok(
        [DocumentOut.model_validate(document) for document in documents],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/{document_id}", response_model=Envelope[DocumentOut], responses=error_responses(401, 404)
)
def get_document(
    document_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Envelope[DocumentOut]:
    return ok(DocumentOut.model_validate(service.get_document(session, user.id, document_id)))


@router.delete(
    "/{document_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(401, 404),
)
def delete_document(document_id: uuid.UUID, user: CurrentUser, session: DbSession) -> Response:
    """Deletes the document with its chunks and embeddings. Past answers keep their citations."""
    service.delete_document(session, user.id, document_id)
    logger.info("document.deleted", extra={"document_id": str(document_id)})
    return Response(status_code=204)
