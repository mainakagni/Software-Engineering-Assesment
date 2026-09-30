import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.deps import CurrentUser
from app.dependencies import DbSession, EmbedderDep, LLMDep, SettingsDep
from app.envelope import Envelope, PageMeta, error_responses, ok
from app.qa import service
from app.qa.schemas import AnswerOut, AskRequest

router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.post(
    "", response_model=Envelope[AnswerOut], responses=error_responses(401, 404, 409, 422, 503)
)
def ask_question(
    body: AskRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
    embedder: EmbedderDep,
    llm: LLMDep,
) -> Envelope[AnswerOut]:
    """Answers from your ready documents (or only the selected ones), with citations.

    When the documents do not contain the answer, `found` is false and the answer says so.
    """
    record = service.ask(
        session, user.id, body.question, body.document_ids,
        embedder=embedder, llm=llm, settings=settings,
    )  # fmt: skip
    return ok(AnswerOut.model_validate(record))


@router.get("", response_model=Envelope[list[AnswerOut]], responses=error_responses(401, 422))
def list_questions(
    user: CurrentUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Envelope[list[AnswerOut]]:
    """Your question history, newest first."""
    records, total = service.list_questions(session, user.id, limit=limit, offset=offset)
    return ok(
        [AnswerOut.model_validate(record) for record in records],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/{question_id}", response_model=Envelope[AnswerOut], responses=error_responses(401, 404)
)
def get_question(
    question_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Envelope[AnswerOut]:
    return ok(AnswerOut.model_validate(service.get_question(session, user.id, question_id)))
