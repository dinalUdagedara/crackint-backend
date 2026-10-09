"""
Prep session service: context loading, message persistence, and the Q&A flows behind the
session routes (/next-question, /chat, /send, /evaluate-answer).

Agent calls raise ValueError when the LLM is unavailable; this module turns those into
HTTP 503 so routes stay thin.
"""

import uuid as uuid_pkg
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.session_qa_agent import (
    NEXT_QUESTION_SENTINEL,
    AnswerEvaluationResult,
    QuestionGenerationResult,
    classify_and_redirect,
    evaluate_answer,
    generate_next_question,
    generate_session_title,
    generate_tutor_chat_reply,
    get_suggested_difficulty,
    summarize_session_feedback,
)
from app.models import JobPosting, Message, PrepSession, Resume
from app.schemas.common import RoleLevel, SenderType, SessionMode

# Update session summary (LLM) only every N FEEDBACK messages to reduce cost.
SUMMARY_UPDATE_EVERY_N = 10


def _agent_unavailable(e: ValueError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(e))


def _as_history(m: Message) -> Dict[str, Any]:
    return {"sender": m.sender, "type": m.type, "content": m.content}


@dataclass
class SessionContext:
    """A prep session with its resume/job entities and the messages stored before this request."""

    session: PrepSession
    resume_entities: Dict[str, List[str]] = field(default_factory=dict)
    job_entities: Dict[str, List[str]] = field(default_factory=dict)
    messages: List[Message] = field(default_factory=list)
    role_level: str = RoleLevel.ASE.value

    @property
    def last_question(self) -> Optional[str]:
        for m in reversed(self.messages):
            if m.type == "QUESTION":
                return m.content
        return None

    @property
    def question_count(self) -> int:
        return sum(1 for m in self.messages if m.type == "QUESTION")

    def history(self, extra: Sequence[Message] = ()) -> List[Dict[str, Any]]:
        """Messages for agent prompts: stored history plus messages added during this request."""
        return [_as_history(m) for m in [*self.messages, *extra]]


# --- Queries ----------------------------------------------------------------


async def list_sessions(
    db: AsyncSession,
    user_id: uuid_pkg.UUID,
    job_posting_id: Optional[uuid_pkg.UUID] = None,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
) -> Tuple[List[PrepSession], int]:
    """User's sessions, most recently updated first, with the total count before paging."""
    base_filter = PrepSession.user_id == user_id
    if job_posting_id is not None:
        base_filter = base_filter & (PrepSession.job_posting_id == job_posting_id)

    total_result = await db.execute(select(func.count()).select_from(PrepSession).where(base_filter))
    total_items = total_result.scalar_one() or 0

    q = select(PrepSession).where(base_filter).order_by(PrepSession.updated_at.desc())
    if offset is not None and limit is not None:
        q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total_items


async def list_messages(db: AsyncSession, session_id: uuid_pkg.UUID) -> List[Message]:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def compute_readiness_from_feedback(db: AsyncSession, session_id: uuid_pkg.UUID) -> Optional[float]:
    """Compute readiness_score as average of FEEDBACK message scores (on request)."""
    result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.type == "FEEDBACK",
        )
    )
    scores: List[float] = []
    for m in result.scalars().all():
        raw = (m.meta or {}).get("score")
        if raw is not None:
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                pass
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


async def load_context(
    db: AsyncSession,
    session_id: uuid_pkg.UUID,
    role_level: Optional[str] = None,
) -> SessionContext:
    """Load prep session with resume, job posting, and messages. Raises 404 if missing."""
    session_obj = await db.get(PrepSession, session_id)
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")

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

    return SessionContext(
        session=session_obj,
        resume_entities=resume_entities,
        job_entities=job_entities,
        messages=await list_messages(db, session_id),
        role_level=role_level or RoleLevel.ASE.value,
    )


async def update_session(
    db: AsyncSession,
    prep_session: PrepSession,
    title: Optional[str] = None,
    mode: Optional[str] = None,
) -> PrepSession:
    """Rename (stored in summary.title) and/or change mode."""
    if title is not None:
        summary_dict = dict(prep_session.summary or {})
        summary_dict["title"] = title
        prep_session.summary = summary_dict
    if mode is not None:
        prep_session.mode = mode
    db.add(prep_session)
    await db.commit()
    await db.refresh(prep_session)
    return prep_session


# --- Building blocks ----------------------------------------------------------


async def save_message(
    db: AsyncSession,
    session_id: uuid_pkg.UUID,
    sender: SenderType,
    type: str,
    content: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Message:
    message = Message(session_id=session_id, sender=sender.value, type=type, content=content, meta=meta or {})
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def ask_next_question(
    db: AsyncSession,
    ctx: SessionContext,
    extra_history: Sequence[Message] = (),
    question_type: Optional[str] = None,
    prefer_difficulty: Optional[str] = None,
) -> Tuple[Message, QuestionGenerationResult]:
    """Generate the next question and store it as an ASSISTANT QUESTION message."""
    question_index = ctx.question_count
    try:
        result = await generate_next_question(
            role_level=ctx.role_level,
            job_entities=ctx.job_entities,
            resume_entities=ctx.resume_entities,
            previous_messages=ctx.history(extra_history),
            question_type=question_type,
            question_index=question_index,
            suggested_difficulty=prefer_difficulty or get_suggested_difficulty(question_index),
        )
    except ValueError as e:
        raise _agent_unavailable(e) from e

    meta: Dict[str, Any] = {}
    if result.difficulty:
        meta["difficulty"] = result.difficulty
    if result.question_type:
        meta["question_type"] = result.question_type
    message = await save_message(db, ctx.session.id, SenderType.ASSISTANT, "QUESTION", result.question, meta)
    return message, result


async def save_redirect(db: AsyncSession, ctx: SessionContext, content: str) -> Message:
    """Store a non-scored assistant reply (greeting/off-topic redirect or tutor reply)."""
    return await save_message(db, ctx.session.id, SenderType.ASSISTANT, "FEEDBACK", content, {"redirect": "true"})


async def classify(question: str, user_message: str) -> Optional[str]:
    """Redirect text, NEXT_QUESTION_SENTINEL, or None for a substantive answer."""
    try:
        return await classify_and_redirect(question=question, user_message=user_message)
    except ValueError as e:
        raise _agent_unavailable(e) from e


async def evaluate_and_save_feedback(
    db: AsyncSession,
    ctx: SessionContext,
    question: str,
    answer: str,
) -> Tuple[Message, AnswerEvaluationResult]:
    try:
        result = await evaluate_answer(
            question=question,
            answer=answer,
            role_level=ctx.role_level,
            job_entities=ctx.job_entities,
            resume_entities=ctx.resume_entities,
        )
    except ValueError as e:
        raise _agent_unavailable(e) from e

    meta: Dict[str, Any] = {"score": str(result.score)}
    if result.dimension_tags:
        meta["dimension_tags"] = ",".join(result.dimension_tags)
    message = await save_message(db, ctx.session.id, SenderType.ASSISTANT, "FEEDBACK", result.feedback, meta)
    return message, result


async def update_session_after_feedback(db: AsyncSession, ctx: SessionContext, last_question: str) -> None:
    """Set a session title once, and refresh the LLM summary every N feedback messages. Best effort."""
    session_obj = ctx.session
    try:
        summary_dict: Dict[str, Any] = dict(session_obj.summary or {})
        if not summary_dict.get("title"):
            title_result = await generate_session_title(
                role_level=ctx.role_level,
                job_entities=ctx.job_entities,
                resume_entities=ctx.resume_entities,
                last_question=last_question,
            )
            if title_result.title:
                summary_dict["title"] = title_result.title
                session_obj.summary = summary_dict
                db.add(session_obj)
                await db.commit()
    except ValueError:
        pass

    feedback_result = await db.execute(
        select(Message).where(
            Message.session_id == session_obj.id,
            Message.type == "FEEDBACK",
        )
    )
    feedback_messages = list(feedback_result.scalars().all())
    if len(feedback_messages) % SUMMARY_UPDATE_EVERY_N != 0:
        return
    # Exclude redirect (greeting/off-topic) messages from summary
    feedback_items = [
        {"content": m.content, "meta": m.meta or {}}
        for m in feedback_messages
        if (m.meta or {}).get("redirect") != "true"
    ]
    try:
        summary_result = await summarize_session_feedback(
            role_level=ctx.role_level,
            feedback_items=feedback_items,
            job_entities=ctx.job_entities,
            resume_entities=ctx.resume_entities,
        )
    except ValueError:
        return  # Keep existing summary; readiness is computed on request
    existing_summary: Dict[str, Any] = dict(session_obj.summary or {})
    existing_summary["strengths"] = summary_result.strengths
    existing_summary["areas_for_improvement"] = summary_result.areas_for_improvement
    session_obj.summary = existing_summary
    db.add(session_obj)
    await db.commit()


# --- Flows ------------------------------------------------------------------


@dataclass
class AnswerOutcome:
    """Result of replying to the current question.

    kind: "skip" (message is the next QUESTION), "redirect" (non-scored FEEDBACK), or
    "evaluated" (scored FEEDBACK; evaluation is set).
    """

    kind: Literal["skip", "redirect", "evaluated"]
    message: Message
    evaluation: Optional[AnswerEvaluationResult] = None


async def handle_answer(
    db: AsyncSession,
    ctx: SessionContext,
    answer: str,
    user_message: Optional[Message] = None,
    prefer_difficulty: Optional[str] = None,
) -> AnswerOutcome:
    """Classify a reply to ctx.last_question, then skip, redirect, or evaluate it.

    user_message: the stored USER message for this reply, if the caller stored one; it is
    included in the history used to generate the next question on skip.
    """
    question = ctx.last_question
    assert question is not None, "handle_answer requires a question in the session"
    extra: Tuple[Message, ...] = (user_message,) if user_message is not None else ()

    redirect_message = await classify(question, answer)
    if redirect_message == NEXT_QUESTION_SENTINEL:
        next_question, _ = await ask_next_question(db, ctx, extra, prefer_difficulty=prefer_difficulty)
        return AnswerOutcome("skip", next_question)
    if redirect_message:
        return AnswerOutcome("redirect", await save_redirect(db, ctx, redirect_message))

    feedback, evaluation = await evaluate_and_save_feedback(db, ctx, question, answer)
    await update_session_after_feedback(db, ctx, question)
    return AnswerOutcome("evaluated", feedback, evaluation)


async def chat_turn(
    db: AsyncSession,
    ctx: SessionContext,
    content: str,
    prefer_difficulty: Optional[str] = None,
) -> Tuple[List[Message], str]:
    """Unified chat turn. Stores the USER message, then replies depending on mode and state.

    Returns the messages created during the turn (in order) and a status message.
    """
    user_message = await save_message(db, ctx.session.id, SenderType.USER, "ANSWER", content)
    new_messages: List[Message] = [user_message]

    if ctx.session.mode == SessionMode.TUTOR_CHAT.value:
        try:
            reply = await generate_tutor_chat_reply(
                role_level=ctx.role_level,
                job_entities=ctx.job_entities,
                resume_entities=ctx.resume_entities,
                previous_messages=ctx.history(),
                user_message=content,
            )
        except ValueError as e:
            raise _agent_unavailable(e) from e
        new_messages.append(await save_redirect(db, ctx, reply))
        return new_messages, "Chat turn processed: tutor reply generated."

    if not ctx.last_question:
        question, _ = await ask_next_question(db, ctx, (user_message,), prefer_difficulty=prefer_difficulty)
        new_messages.append(question)
        return new_messages, "Chat turn processed: first question generated."

    outcome = await handle_answer(db, ctx, content, user_message, prefer_difficulty)
    new_messages.append(outcome.message)
    if outcome.kind == "skip":
        return new_messages, "Chat turn processed: next question (user skipped)."
    if outcome.kind == "redirect":
        return new_messages, "Chat turn processed: redirect response (greeting/off-topic)."

    try:
        next_question, _ = await ask_next_question(
            db, ctx, (user_message, outcome.message), prefer_difficulty=prefer_difficulty
        )
    except HTTPException:
        # If next-question generation fails, still return feedback
        return new_messages, "Chat turn processed: feedback stored (next question generation failed)."
    new_messages.append(next_question)
    return new_messages, "Chat turn processed: feedback and next question stored."
