"""
Prep session and message endpoints (MVP chat session APIs).
"""

from typing import Any, Dict, List, Optional
import uuid as uuid_pkg

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.session_qa_agent import (
    NEXT_QUESTION_SENTINEL,
    classify_and_redirect,
    evaluate_answer,
    generate_next_question,
    summarize_session_feedback,
    generate_session_title,
    generate_tutor_chat_reply,
)
from app.api.deps import get_current_user, get_db
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
from app.common.http_response_model import CommonResponse
from app.models import JobPosting, Message, PrepSession, Resume, User
from app.schemas.common import RoleLevel, SenderType, SessionMode

router = APIRouter()

# Update session summary (LLM) only every N FEEDBACK messages to reduce cost.
SUMMARY_UPDATE_EVERY_N = 10


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
    summary="List the current user's prep sessions.",
)
async def list_prep_sessions(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(PrepSession)
        .where(PrepSession.user_id == current_user.id)
        .order_by(PrepSession.updated_at.desc())
    )
    rows = list(result.scalars().all())
    payload = [PrepSessionRead.model_validate(row) for row in rows]
    return CommonResponse(
        success=True,
        message="Prep sessions retrieved successfully",
        payload=payload,
    )


async def _compute_readiness_from_feedback(
    db: AsyncSession, session_id: uuid_pkg.UUID
) -> Optional[float]:
    """Compute readiness_score as average of FEEDBACK message scores (on request)."""
    result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.type == "FEEDBACK",
        )
    )
    messages = list(result.scalars().all())
    scores: List[float] = []
    for m in messages:
        raw = (m.meta or {}).get("score")
        if raw is not None:
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                pass
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


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
    readiness_score = await _compute_readiness_from_feedback(db, prep_session.id)
    payload_dict = PrepSessionRead.model_validate(prep_session).model_dump()
    payload_dict["readiness_score"] = readiness_score
    return CommonResponse(
        success=True,
        message="Prep session retrieved successfully",
        payload=PrepSessionRead(**payload_dict),
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
    if body.title is not None:
        summary_dict = dict(prep_session.summary or {})
        summary_dict["title"] = body.title
        prep_session.summary = summary_dict

    if body.mode is not None:
        prep_session.mode = body.mode.value

    db.add(prep_session)
    await db.commit()
    await db.refresh(prep_session)

    readiness_score = await _compute_readiness_from_feedback(db, prep_session.id)
    payload_dict = PrepSessionRead.model_validate(prep_session).model_dump()
    payload_dict["readiness_score"] = readiness_score

    return CommonResponse(
        success=True,
        message="Prep session updated successfully",
        payload=PrepSessionRead(**payload_dict),
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
    result = await db.execute(
        select(Message)
        .where(Message.session_id == prep_session.id)
        .order_by(Message.created_at.asc())
    )
    rows = list(result.scalars().all())
    payload = [MessageRead.model_validate(row) for row in rows]
    return CommonResponse(
        success=True,
        message="Messages retrieved successfully",
        payload=payload,
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
    message = Message(
        session_id=prep_session.id,
        sender=body.sender.value,
        type=body.type.value,
        content=body.content,
        meta=body.metadata,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

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
    result = await db.execute(
        select(Message)
        .where(Message.session_id == prep_session.id)
        .order_by(Message.created_at.asc())
    )
    rows = list(result.scalars().all())
    messages = [MessageRead.model_validate(row) for row in rows]

    readiness_score = await _compute_readiness_from_feedback(db, prep_session.id)
    base_dict = PrepSessionRead.model_validate(prep_session).model_dump()
    base_dict["readiness_score"] = readiness_score
    combined = PrepSessionWithMessages(
        **base_dict,
        messages=messages,
    )
    return CommonResponse(
        success=True,
        message="Prep session with messages retrieved successfully",
        payload=combined,
    )


# --- Session Q&A (requires SESSION_QA_AGENT_ENABLED and OPENAI_API_KEY) ---


async def _load_session_context(db: AsyncSession, session_id: uuid_pkg.UUID):
    """Load prep session with resume, job posting, and messages. Returns (session_obj, resume_entities, job_entities, messages_list)."""
    session_obj = await db.get(PrepSession, session_id)
    if session_obj is None:
        return None, {}, {}, []

    resume_entities: Dict[str, List[str]] = {}
    if session_obj.resume_id:
        resume = await db.get(Resume, session_obj.resume_id)
        if resume and resume.entities:
            resume_entities = dict(resume.entities)

    job_entities: Dict[str, List[str]] = {}
    if session_obj.job_posting_id:
        job = await db.get(JobPosting, session_obj.job_posting_id)
        if job and job.entities:
            job_entities = dict(job.entities)

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages_list = list(result.scalars().all())

    return session_obj, resume_entities, job_entities, messages_list


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
    session_obj, resume_entities, job_entities, messages_list = (
        await _load_session_context(db, prep_session.id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")

    role_level = (body.role_level or RoleLevel.ASE).value
    previous_messages: List[Dict[str, Any]] = [
        {"sender": m.sender, "type": m.type, "content": m.content}
        for m in messages_list
    ]
    question_type = body.question_type if body.question_type else None

    try:
        result = await generate_next_question(
            role_level=role_level,
            job_entities=job_entities,
            resume_entities=resume_entities,
            previous_messages=previous_messages,
            question_type=question_type,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    meta: Dict[str, Any] = {}
    if result.difficulty:
        meta["difficulty"] = result.difficulty
    if result.question_type:
        meta["question_type"] = result.question_type

    message = Message(
        session_id=prep_session.id,
        sender=SenderType.ASSISTANT.value,
        type="QUESTION",
        content=result.question,
        meta=meta,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    payload = NextQuestionPayload(
        question=result.question,
        difficulty=result.difficulty,
        question_type=result.question_type,
        message_id=message.id,
    )
    return CommonResponse(
        success=True,
        message="Next question generated and stored.",
        payload=payload,
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
    session_obj, resume_entities, job_entities, messages_list = (
        await _load_session_context(db, prep_session.id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")
    session_id = prep_session.id

    # Find last QUESTION, if any
    last_question_content: Optional[str] = None
    for m in reversed(messages_list):
        if m.type == "QUESTION":
            last_question_content = m.content
            break

    # 1. Store USER message for this turn
    user_message = Message(
        session_id=session_id,
        sender=SenderType.USER.value,
        type="ANSWER",
        content=body.content,
        meta={},
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    new_messages: List[MessageRead] = [MessageRead.model_validate(user_message)]

    # Case: Conversational Tutor Mode
    if session_obj.mode == SessionMode.TUTOR_CHAT.value:
        role_level = RoleLevel.ASE.value
        previous_messages: List[Dict[str, Any]] = [
            {"sender": m.sender, "type": m.type, "content": m.content}
            for m in messages_list
        ]
        
        try:
            tutor_reply = await generate_tutor_chat_reply(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                previous_messages=previous_messages,
                user_message=body.content,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=503,
                detail=str(e),
            ) from e

        assistant_message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="FEEDBACK",
            content=tutor_reply,
            meta={"redirect": "true"},
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        new_messages.append(MessageRead.model_validate(assistant_message))

        return CommonResponse(
            success=True,
            message="Chat turn processed: tutor reply generated.",
            payload=ChatTurnPayload(new_messages=new_messages),
        )

    # Case A: no QUESTION yet -> start interview by asking the first question
    if not last_question_content:
        role_level = RoleLevel.ASE.value
        previous_messages: List[Dict[str, Any]] = [
            {"sender": m.sender, "type": m.type, "content": m.content}
            for m in messages_list
        ] + [
            {
                "sender": user_message.sender,
                "type": user_message.type,
                "content": user_message.content,
            }
        ]
        try:
            result = await generate_next_question(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                previous_messages=previous_messages,
                question_type=None,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=503,
                detail=str(e),
            ) from e

        meta: Dict[str, Any] = {}
        if result.difficulty:
            meta["difficulty"] = result.difficulty
        if result.question_type:
            meta["question_type"] = result.question_type

        question_message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="QUESTION",
            content=result.question,
            meta=meta,
        )
        db.add(question_message)
        await db.commit()
        await db.refresh(question_message)

        new_messages.append(MessageRead.model_validate(question_message))

        return CommonResponse(
            success=True,
            message="Chat turn processed: first question generated.",
            payload=ChatTurnPayload(new_messages=new_messages),
        )

    # Case B: we have a QUESTION -> classify + maybe evaluate and ask next question
    role_level = RoleLevel.ASE.value

    # 2. Classify greeting/off-topic vs substantive answer
    try:
        redirect_message = await classify_and_redirect(
            question=last_question_content,
            user_message=body.content,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    if redirect_message == NEXT_QUESTION_SENTINEL:
        # User asked to skip to next question: generate and return it (no feedback).
        previous_messages_skip: List[Dict[str, Any]] = [
            {"sender": m.sender, "type": m.type, "content": m.content}
            for m in messages_list
        ] + [
            {
                "sender": user_message.sender,
                "type": user_message.type,
                "content": user_message.content,
            },
        ]
        try:
            next_q_result = await generate_next_question(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                previous_messages=previous_messages_skip,
                question_type=None,
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        next_meta: Dict[str, Any] = {}
        if next_q_result.difficulty:
            next_meta["difficulty"] = next_q_result.difficulty
        if next_q_result.question_type:
            next_meta["question_type"] = next_q_result.question_type
        next_question_message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="QUESTION",
            content=next_q_result.question,
            meta=next_meta,
        )
        db.add(next_question_message)
        await db.commit()
        await db.refresh(next_question_message)
        new_messages.append(MessageRead.model_validate(next_question_message))
        return CommonResponse(
            success=True,
            message="Chat turn processed: next question (user skipped).",
            payload=ChatTurnPayload(new_messages=new_messages),
        )

    if redirect_message:
        assistant_message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="FEEDBACK",
            content=redirect_message,
            meta={"redirect": "true"},
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        new_messages.append(MessageRead.model_validate(assistant_message))

        return CommonResponse(
            success=True,
            message="Chat turn processed: redirect response (greeting/off-topic).",
            payload=ChatTurnPayload(new_messages=new_messages),
        )

    # 3. Substantive answer: evaluate then generate next question
    try:
        result = await evaluate_answer(
            question=last_question_content,
            answer=body.content,
            role_level=role_level,
            job_entities=job_entities,
            resume_entities=resume_entities,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    meta: Dict[str, Any] = {"score": str(result.score)}
    if result.dimension_tags:
        meta["dimension_tags"] = ",".join(result.dimension_tags)

    feedback_message = Message(
        session_id=session_id,
        sender=SenderType.ASSISTANT.value,
        type="FEEDBACK",
        content=result.feedback,
        meta=meta,
    )
    db.add(feedback_message)
    await db.commit()
    await db.refresh(feedback_message)

    new_messages.append(MessageRead.model_validate(feedback_message))

    # Optional: session title once when user starts chatting
    try:
        summary_dict: Dict[str, Any] = dict(session_obj.summary or {})
        if not summary_dict.get("title"):
            title_result = await generate_session_title(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                last_question=last_question_content,
            )
            if title_result.title:
                summary_dict["title"] = title_result.title
                session_obj.summary = summary_dict
                db.add(session_obj)
                await db.commit()
    except ValueError:
        pass

    # Session summary (LLM) every N FEEDBACK messages
    feedback_result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.type == "FEEDBACK",
        )
    )
    feedback_messages = list(feedback_result.scalars().all())
    if len(feedback_messages) % SUMMARY_UPDATE_EVERY_N == 0:
        feedback_items = [
            {"content": m.content, "meta": m.meta or {}}
            for m in feedback_messages
            if (m.meta or {}).get("redirect") != "true"
        ]
        try:
            summary_result = await summarize_session_feedback(
                role_level=role_level,
                feedback_items=feedback_items,
                job_entities=job_entities,
                resume_entities=resume_entities,
            )
            existing_summary: Dict[str, Any] = dict(session_obj.summary or {})
            existing_summary["strengths"] = summary_result.strengths
            existing_summary["areas_for_improvement"] = (
                summary_result.areas_for_improvement
            )
            session_obj.summary = existing_summary
            db.add(session_obj)
            await db.commit()
        except ValueError:
            pass

    # Generate next question after providing feedback
    previous_messages_for_next_q: List[Dict[str, Any]] = [
        {"sender": m.sender, "type": m.type, "content": m.content}
        for m in messages_list
    ] + [
        {
            "sender": user_message.sender,
            "type": user_message.type,
            "content": user_message.content,
        },
        {
            "sender": feedback_message.sender,
            "type": feedback_message.type,
            "content": feedback_message.content,
        },
    ]

    try:
        next_q_result = await generate_next_question(
            role_level=role_level,
            job_entities=job_entities,
            resume_entities=resume_entities,
            previous_messages=previous_messages_for_next_q,
            question_type=None,
        )
    except ValueError as e:
        # If next-question generation fails, still return feedback
        return CommonResponse(
            success=True,
            message="Chat turn processed: feedback stored (next question generation failed).",
            payload=ChatTurnPayload(new_messages=new_messages),
        )

    next_meta: Dict[str, Any] = {}
    if next_q_result.difficulty:
        next_meta["difficulty"] = next_q_result.difficulty
    if next_q_result.question_type:
        next_meta["question_type"] = next_q_result.question_type

    next_question_message = Message(
        session_id=session_id,
        sender=SenderType.ASSISTANT.value,
        type="QUESTION",
        content=next_q_result.question,
        meta=next_meta,
    )
    db.add(next_question_message)
    await db.commit()
    await db.refresh(next_question_message)

    new_messages.append(MessageRead.model_validate(next_question_message))

    return CommonResponse(
        success=True,
        message="Chat turn processed: feedback and next question stored.",
        payload=ChatTurnPayload(new_messages=new_messages),
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
    session_obj, resume_entities, job_entities, messages_list = (
        await _load_session_context(db, prep_session.id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")
    session_id = prep_session.id

    last_question_content: Optional[str] = None
    for m in reversed(messages_list):
        if m.type == "QUESTION":
            last_question_content = m.content
            break
    if not last_question_content:
        raise HTTPException(
            status_code=400,
            detail="No question in this session to reply to. Add a question first (e.g. via next-question).",
        )

    # 1. Store user message (USER, ANSWER)
    user_message = Message(
        session_id=session_id,
        sender=SenderType.USER.value,
        type="ANSWER",
        content=body.content,
        meta={},
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    user_message_id = user_message.id

    role_level = RoleLevel.ASE.value

    # 2. Classify: redirect (greeting/off-topic) or full evaluation
    try:
        redirect_message = await classify_and_redirect(
            question=last_question_content,
            user_message=body.content,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    if redirect_message == NEXT_QUESTION_SENTINEL:
        # User asked to skip: generate next question and return it (no redirect feedback).
        previous_messages_skip: List[Dict[str, Any]] = [
            {"sender": m.sender, "type": m.type, "content": m.content}
            for m in messages_list
        ] + [
            {
                "sender": user_message.sender,
                "type": user_message.type,
                "content": user_message.content,
            },
        ]
        try:
            next_q_result = await generate_next_question(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                previous_messages=previous_messages_skip,
                question_type=None,
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        next_meta: Dict[str, Any] = {}
        if next_q_result.difficulty:
            next_meta["difficulty"] = next_q_result.difficulty
        if next_q_result.question_type:
            next_meta["question_type"] = next_q_result.question_type
        next_question_message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="QUESTION",
            content=next_q_result.question,
            meta=next_meta,
        )
        db.add(next_question_message)
        await db.commit()
        await db.refresh(next_question_message)
        payload = SendReplyPayload(
            user_message_id=user_message_id,
            feedback=next_q_result.question,
            score=None,
            dimension_tags=[],
            message_id=next_question_message.id,
            redirect=False,
        )
        return CommonResponse(
            success=True,
            message="Next question generated (user skipped).",
            payload=payload,
        )

    if redirect_message:
        assistant_message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="FEEDBACK",
            content=redirect_message,
            meta={"redirect": "true"},
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)
        payload = SendReplyPayload(
            user_message_id=user_message_id,
            feedback=redirect_message,
            score=None,
            dimension_tags=[],
            message_id=assistant_message.id,
            redirect=True,
        )
        return CommonResponse(
            success=True,
            message="Reply stored; redirect response (greeting/off-topic).",
            payload=payload,
        )

    # 3. Full evaluation
    try:
        result = await evaluate_answer(
            question=last_question_content,
            answer=body.content,
            role_level=role_level,
            job_entities=job_entities,
            resume_entities=resume_entities,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    meta: Dict[str, Any] = {"score": str(result.score)}
    if result.dimension_tags:
        meta["dimension_tags"] = ",".join(result.dimension_tags)

    assistant_message = Message(
        session_id=session_id,
        sender=SenderType.ASSISTANT.value,
        type="FEEDBACK",
        content=result.feedback,
        meta=meta,
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)

    # Optional: session title once when user starts chatting
    try:
        summary_dict: Dict[str, Any] = dict(session_obj.summary or {})
        if not summary_dict.get("title"):
            title_result = await generate_session_title(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                last_question=last_question_content,
            )
            if title_result.title:
                summary_dict["title"] = title_result.title
                session_obj.summary = summary_dict
                db.add(session_obj)
                await db.commit()
    except ValueError:
        pass

    # Session summary (LLM) every N FEEDBACK messages
    feedback_result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.type == "FEEDBACK",
        )
    )
    feedback_messages = list(feedback_result.scalars().all())
    if len(feedback_messages) % SUMMARY_UPDATE_EVERY_N == 0:
        feedback_items = [
            {"content": m.content, "meta": m.meta or {}}
            for m in feedback_messages
            if (m.meta or {}).get("redirect") != "true"
        ]
        try:
            summary_result = await summarize_session_feedback(
                role_level=role_level,
                feedback_items=feedback_items,
                job_entities=job_entities,
                resume_entities=resume_entities,
            )
            existing_summary: Dict[str, Any] = dict(session_obj.summary or {})
            existing_summary["strengths"] = summary_result.strengths
            existing_summary["areas_for_improvement"] = (
                summary_result.areas_for_improvement
            )
            session_obj.summary = existing_summary
            db.add(session_obj)
            await db.commit()
        except ValueError:
            pass

    payload = SendReplyPayload(
        user_message_id=user_message_id,
        feedback=result.feedback,
        score=result.score,
        dimension_tags=result.dimension_tags,
        message_id=assistant_message.id,
        redirect=False,
    )
    return CommonResponse(
        success=True,
        message="Reply sent and feedback stored.",
        payload=payload,
    )


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
    session_obj, resume_entities, job_entities, messages_list = (
        await _load_session_context(db, prep_session.id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")
    session_id = prep_session.id

    last_question_content: Optional[str] = None
    for m in reversed(messages_list):
        if m.type == "QUESTION":
            last_question_content = m.content
            break
    if not last_question_content:
        raise HTTPException(
            status_code=400,
            detail="No question in this session to evaluate against. Add a question first (e.g. via next-question).",
        )

    role_level = RoleLevel.ASE.value

    # ChatGPT-style: if user message is greeting/off-topic, return a friendly redirect (no evaluation)
    try:
        redirect_message = await classify_and_redirect(
            question=last_question_content,
            user_message=body.answer,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    if redirect_message == NEXT_QUESTION_SENTINEL:
        previous_messages_skip: List[Dict[str, Any]] = [
            {"sender": m.sender, "type": m.type, "content": m.content}
            for m in messages_list
        ]
        try:
            next_q_result = await generate_next_question(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                previous_messages=previous_messages_skip,
                question_type=None,
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        next_meta: Dict[str, Any] = {}
        if next_q_result.difficulty:
            next_meta["difficulty"] = next_q_result.difficulty
        if next_q_result.question_type:
            next_meta["question_type"] = next_q_result.question_type
        next_question_message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="QUESTION",
            content=next_q_result.question,
            meta=next_meta,
        )
        db.add(next_question_message)
        await db.commit()
        await db.refresh(next_question_message)
        payload = EvaluateAnswerPayload(
            feedback=next_q_result.question,
            score=None,
            dimension_tags=[],
            message_id=next_question_message.id,
            redirect=False,
        )
        return CommonResponse(
            success=True,
            message="Next question generated (user skipped).",
            payload=payload,
        )

    if redirect_message:
        message = Message(
            session_id=session_id,
            sender=SenderType.ASSISTANT.value,
            type="FEEDBACK",
            content=redirect_message,
            meta={"redirect": "true"},
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        payload = EvaluateAnswerPayload(
            feedback=redirect_message,
            score=None,
            dimension_tags=[],
            message_id=message.id,
            redirect=True,
        )
        return CommonResponse(
            success=True,
            message="Redirect response stored (greeting/off-topic).",
            payload=payload,
        )

    try:
        result = await evaluate_answer(
            question=last_question_content,
            answer=body.answer,
            role_level=role_level,
            job_entities=job_entities,
            resume_entities=resume_entities,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    meta: Dict[str, Any] = {
        "score": str(result.score),
    }
    if result.dimension_tags:
        meta["dimension_tags"] = ",".join(result.dimension_tags)

    message = Message(
        session_id=session_id,
        sender=SenderType.ASSISTANT.value,
        type="FEEDBACK",
        content=result.feedback,
        meta=meta,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Optionally generate a human-friendly session title once, when the user starts chatting
    try:
        summary_dict: Dict[str, Any] = dict(session_obj.summary or {})
        if not summary_dict.get("title"):
            title_result = await generate_session_title(
                role_level=role_level,
                job_entities=job_entities,
                resume_entities=resume_entities,
                last_question=last_question_content,
            )
            if title_result.title:
                summary_dict["title"] = title_result.title
                session_obj.summary = summary_dict
                db.add(session_obj)
                await db.commit()
    except ValueError:
        # If title generation fails, continue without blocking the flow
        pass

    # Update session summary (LLM) only every N FEEDBACK messages
    feedback_result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.type == "FEEDBACK",
        )
    )
    feedback_messages = list(feedback_result.scalars().all())
    if len(feedback_messages) % SUMMARY_UPDATE_EVERY_N == 0:
        # Exclude redirect (greeting/off-topic) messages from summary
        feedback_items = [
            {"content": m.content, "meta": m.meta or {}}
            for m in feedback_messages
            if (m.meta or {}).get("redirect") != "true"
        ]
        try:
            summary_result = await summarize_session_feedback(
                role_level=role_level,
                feedback_items=feedback_items,
                job_entities=job_entities,
                resume_entities=resume_entities,
            )
            existing_summary: Dict[str, Any] = dict(session_obj.summary or {})
            existing_summary["strengths"] = summary_result.strengths
            existing_summary["areas_for_improvement"] = (
                summary_result.areas_for_improvement
            )
            session_obj.summary = existing_summary
            db.add(session_obj)
            await db.commit()
        except ValueError:
            pass  # Keep existing summary; readiness is computed on request

    payload = EvaluateAnswerPayload(
        feedback=result.feedback,
        score=result.score,
        dimension_tags=result.dimension_tags,
        message_id=message.id,
    )
    return CommonResponse(
        success=True,
        message="Answer evaluated and feedback stored.",
        payload=payload,
    )
