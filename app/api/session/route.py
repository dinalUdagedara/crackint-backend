"""
Prep session and message endpoints (MVP chat session APIs).

Business logic lives in app.api.session.service; routes validate, call it, and shape responses.
"""

from typing import Any, Dict, List, Optional
import uuid as uuid_pkg

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.session import service
from app.api.session.schemas import (
    ChatRequest,
    ChatTurnPayload,
    EvaluateAnswerRequest,
    EvaluateAnswerPayload,
    MessageCreate,
    MessageRead,
    NextQuestionPayload,
    NextQuestionRequest,
    PrepSessionCreate,
    PrepSessionRead,
    PrepSessionUpdate,
    PrepSessionWithMessages,
    SendReplyPayload,
    SendReplyRequest,
)
from app.common.http_response_model import CommonResponse, PageMeta
from app.models import PrepSession, User
from app.schemas.common import SenderType

router = APIRouter()

DEFAULT_SESSION_PAGE_SIZE = 20
MAX_SESSION_PAGE_SIZE = 100


async def get_own_prep_session(
    session_id: uuid_pkg.UUID = Path(..., description="Preparation session ID."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PrepSession:
    """Load prep session by ID; raise 404 if not found or not owned by current user."""
    record = await db.get(PrepSession, session_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Prep session not found.")
    return record


async def _read_with_readiness(db: AsyncSession, prep_session: PrepSession) -> Dict[str, Any]:
    payload_dict = PrepSessionRead.model_validate(prep_session).model_dump()
    payload_dict["readiness_score"] = await service.compute_readiness_from_feedback(db, prep_session.id)
    return payload_dict


def _require_question(ctx: service.SessionContext, action: str) -> str:
    if not ctx.last_question:
        raise HTTPException(
            status_code=400,
            detail=f"No question in this session to {action}. Add a question first (e.g. via next-question).",
        )
    return ctx.last_question


@router.post(
    "",
    response_model=CommonResponse[PrepSessionRead],
    name="Create prep session",
    summary="Create a new preparation session linking user, resume, and job posting.",
)
async def create_prep_session(
    body: PrepSessionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    record = PrepSession(
        user_id=current_user.id,
        resume_id=body.resume_id,
        job_posting_id=body.job_posting_id,
        mode=body.mode.value,
        status="ACTIVE",
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return CommonResponse(
        success=True,
        message="Prep session created successfully",
        payload=PrepSessionRead.model_validate(record),
    )


@router.get(
    "",
    response_model=CommonResponse[List[PrepSessionRead]],
    name="List prep sessions",
    summary="List the current user's prep sessions, optionally filtered by job and paginated.",
)
async def list_prep_sessions(
    job_posting_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Filter sessions by job posting ID.",
    ),
    page: Optional[int] = Query(
        default=None,
        ge=1,
        description="Page number (1-based). If omitted, returns all matching sessions without pagination.",
    ),
    page_size: Optional[int] = Query(
        default=None,
        ge=1,
        le=MAX_SESSION_PAGE_SIZE,
        description="Items per page. Used only when page is provided.",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    use_pagination = page is not None and page_size is not None
    rows, total_items = await service.list_sessions(
        session,
        current_user.id,
        job_posting_id=job_posting_id,
        offset=(page - 1) * page_size if use_pagination else None,
        limit=page_size if use_pagination else None,
    )
    payload = [PrepSessionRead.model_validate(row) for row in rows]
    meta = None
    if use_pagination:
        meta = PageMeta(
            page=page,
            page_size=page_size,
            total_pages=max(1, (total_items + page_size - 1) // page_size),
            total_items=total_items,
        )
    return CommonResponse(
        success=True,
        message="Prep sessions retrieved successfully",
        payload=payload,
        meta=meta,
    )


@router.get(
    "/{session_id}",
    response_model=CommonResponse[PrepSessionRead],
    name="Get prep session by ID",
    summary="Get a single preparation session by ID (without messages).",
)
async def get_prep_session(
    prep_session: PrepSession = Depends(get_own_prep_session),
    db: AsyncSession = Depends(get_db),
):
    return CommonResponse(
        success=True,
        message="Prep session retrieved successfully",
        payload=PrepSessionRead(**await _read_with_readiness(db, prep_session)),
    )


@router.patch(
    "/{session_id}",
    response_model=CommonResponse[PrepSessionRead],
    name="Update prep session",
    summary="Update a prep session (e.g. title or mode).",
)
async def update_prep_session(
    body: PrepSessionUpdate,
    prep_session: PrepSession = Depends(get_own_prep_session),
    db: AsyncSession = Depends(get_db),
):
    await service.update_session(
        db, prep_session, title=body.title, mode=body.mode.value if body.mode else None
    )
    return CommonResponse(
        success=True,
        message="Prep session updated successfully",
        payload=PrepSessionRead(**await _read_with_readiness(db, prep_session)),
    )


@router.delete(
    "/{session_id}",
    response_model=CommonResponse[Dict[str, Any]],
    name="Delete prep session",
    summary="Delete a preparation session by ID (messages are deleted via FK cascade).",
)
async def delete_prep_session(
    prep_session: PrepSession = Depends(get_own_prep_session),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(prep_session)
    await db.commit()

    return CommonResponse(
        success=True,
        message="Prep session deleted successfully",
        payload={"id": str(prep_session.id)},
    )


@router.get(
    "/{session_id}/messages",
    response_model=CommonResponse[List[MessageRead]],
    name="List messages in a prep session",
    summary="List all chat messages in a preparation session.",
)
async def list_session_messages(
    prep_session: PrepSession = Depends(get_own_prep_session),
    db: AsyncSession = Depends(get_db),
):
    rows = await service.list_messages(db, prep_session.id)
    return CommonResponse(
        success=True,
        message="Messages retrieved successfully",
        payload=[MessageRead.model_validate(row) for row in rows],
    )


@router.post(
    "/{session_id}/messages",
    response_model=CommonResponse[MessageRead],
    name="Append message to prep session",
    summary="Append a new chat message (question, answer, or feedback) to an existing prep session.",
)
async def append_message(
    prep_session: PrepSession = Depends(get_own_prep_session),
    body: MessageCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    message = await service.save_message(
        db, prep_session.id, body.sender, body.type.value, body.content, body.metadata
    )
    return CommonResponse(
        success=True,
        message="Message appended successfully",
        payload=MessageRead.model_validate(message),
    )


@router.get(
    "/{session_id}/with-messages",
    response_model=CommonResponse[PrepSessionWithMessages],
    name="Get prep session with messages",
    summary="Get a session including its ordered messages.",
)
async def get_session_with_messages(
    prep_session: PrepSession = Depends(get_own_prep_session),
    db: AsyncSession = Depends(get_db),
):
    rows = await service.list_messages(db, prep_session.id)
    combined = PrepSessionWithMessages(
        **await _read_with_readiness(db, prep_session),
        messages=[MessageRead.model_validate(row) for row in rows],
    )
    return CommonResponse(
        success=True,
        message="Prep session with messages retrieved successfully",
        payload=combined,
    )


# --- Session Q&A (requires SESSION_QA_AGENT_ENABLED and OPENAI_API_KEY) ---


@router.post(
    "/{session_id}/next-question",
    response_model=CommonResponse[NextQuestionPayload],
    name="Generate next question",
    summary="Generate the next interview question for this session and store it as a message.",
)
async def post_next_question(
    prep_session: PrepSession = Depends(get_own_prep_session),
    body: NextQuestionRequest = NextQuestionRequest(),
    db: AsyncSession = Depends(get_db),
):
    ctx = await service.load_context(
        db, prep_session.id, role_level=body.role_level.value if body.role_level else None
    )
    message, result = await service.ask_next_question(
        db,
        ctx,
        question_type=body.question_type or None,
        prefer_difficulty=body.prefer_difficulty,
    )
    return CommonResponse(
        success=True,
        message="Next question generated and stored.",
        payload=NextQuestionPayload(
            question=result.question,
            difficulty=result.difficulty,
            question_type=result.question_type,
            message_id=message.id,
        ),
    )


@router.post(
    "/{session_id}/chat",
    response_model=CommonResponse[ChatTurnPayload],
    name="Chat turn (unified)",
    summary="Unified chat endpoint: store USER message, then redirect or evaluate and maybe ask next question.",
)
async def post_chat_turn(
    prep_session: PrepSession = Depends(get_own_prep_session),
    body: ChatRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    ctx = await service.load_context(db, prep_session.id)
    new_messages, status_message = await service.chat_turn(db, ctx, body.content, body.prefer_difficulty)
    return CommonResponse(
        success=True,
        message=status_message,
        payload=ChatTurnPayload(new_messages=[MessageRead.model_validate(m) for m in new_messages]),
    )


@router.post(
    "/{session_id}/send",
    response_model=CommonResponse[SendReplyPayload],
    name="Send reply",
    summary="Send the user's message, store it, and return assistant response (redirect or evaluation feedback) in one call.",
)
async def post_send(
    prep_session: PrepSession = Depends(get_own_prep_session),
    body: SendReplyRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    ctx = await service.load_context(db, prep_session.id)
    _require_question(ctx, "reply to")
    user_message = await service.save_message(db, prep_session.id, SenderType.USER, "ANSWER", body.content)
    outcome = await service.handle_answer(db, ctx, body.content, user_message, body.prefer_difficulty)

    evaluation = outcome.evaluation
    payload = SendReplyPayload(
        user_message_id=user_message.id,
        feedback=outcome.message.content,
        score=evaluation.score if evaluation else None,
        dimension_tags=evaluation.dimension_tags if evaluation else [],
        message_id=outcome.message.id,
        redirect=outcome.kind == "redirect",
    )
    status_message = {
        "skip": "Next question generated (user skipped).",
        "redirect": "Reply stored; redirect response (greeting/off-topic).",
        "evaluated": "Reply sent and feedback stored.",
    }[outcome.kind]
    return CommonResponse(success=True, message=status_message, payload=payload)


@router.post(
    "/{session_id}/evaluate-answer",
    response_model=CommonResponse[EvaluateAnswerPayload],
    name="Evaluate answer",
    summary="Evaluate the candidate's answer (against the last question) and store feedback as a message.",
)
async def post_evaluate_answer(
    prep_session: PrepSession = Depends(get_own_prep_session),
    body: EvaluateAnswerRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    ctx = await service.load_context(db, prep_session.id)
    _require_question(ctx, "evaluate against")
    # The answer itself is not stored here (callers append it via /messages).
    outcome = await service.handle_answer(db, ctx, body.answer, prefer_difficulty=body.prefer_difficulty)

    evaluation = outcome.evaluation
    payload = EvaluateAnswerPayload(
        feedback=outcome.message.content,
        score=evaluation.score if evaluation else None,
        dimension_tags=evaluation.dimension_tags if evaluation else [],
        message_id=outcome.message.id,
        redirect=outcome.kind == "redirect",
    )
    status_message = {
        "skip": "Next question generated (user skipped).",
        "redirect": "Redirect response stored (greeting/off-topic).",
        "evaluated": "Answer evaluated and feedback stored.",
    }[outcome.kind]
    return CommonResponse(success=True, message=status_message, payload=payload)
