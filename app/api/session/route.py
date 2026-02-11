"""
Prep session and message endpoints (MVP chat session APIs).
"""

from typing import List
import uuid as uuid_pkg

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.session.schemas import (
    MessageCreate,
    MessageRead,
    PrepSessionCreate,
    PrepSessionRead,
    PrepSessionWithMessages,
)
from app.common.http_response_model import CommonResponse
from app.models import Message, PrepSession

router = APIRouter()


@router.post(
    "",
    response_model=CommonResponse[PrepSessionRead],
    name="Create prep session",
    summary="Create a new preparation session linking user, resume, and job posting.",
)
async def create_prep_session(
    body: PrepSessionCreate,
    session: AsyncSession = Depends(get_db),
):
    record = PrepSession(
        user_id=body.user_id,
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
    summary="List all prep sessions (optionally filter by user).",
)
async def list_prep_sessions(
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(PrepSession).order_by(PrepSession.updated_at.desc())
    )
    rows = list(result.scalars().all())
    payload = [PrepSessionRead.model_validate(row) for row in rows]
    return CommonResponse(
        success=True,
        message="Prep sessions retrieved successfully",
        payload=payload,
    )


@router.get(
    "/{session_id}",
    response_model=CommonResponse[PrepSessionRead],
    name="Get prep session by ID",
    summary="Get a single preparation session by ID (without messages).",
)
async def get_prep_session(
    session_id: uuid_pkg.UUID = Path(..., description="Preparation session ID."),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(PrepSession, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")
    return CommonResponse(
        success=True,
        message="Prep session retrieved successfully",
        payload=PrepSessionRead.model_validate(record),
    )


@router.get(
    "/{session_id}/messages",
    response_model=CommonResponse[List[MessageRead]],
    name="List messages in a prep session",
    summary="List all chat messages in a preparation session.",
)
async def list_session_messages(
    session_id: uuid_pkg.UUID = Path(..., description="Preparation session ID."),
    db: AsyncSession = Depends(get_db),
):
    # Ensure session exists
    session_obj = await db.get(PrepSession, session_id)
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
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
    session_id: uuid_pkg.UUID = Path(..., description="Preparation session ID."),
    body: MessageCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    session_obj = await db.get(PrepSession, session_id)
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")

    message = Message(
        session_id=session_id,
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
    session_id: uuid_pkg.UUID = Path(..., description="Preparation session ID."),
    db: AsyncSession = Depends(get_db),
):
    session_obj = await db.get(PrepSession, session_id)
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Prep session not found.")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    rows = list(result.scalars().all())
    messages = [MessageRead.model_validate(row) for row in rows]

    base = PrepSessionRead.model_validate(session_obj)
    combined = PrepSessionWithMessages(
        **base.model_dump(),
        messages=messages,
    )
    return CommonResponse(
        success=True,
        message="Prep session with messages retrieved successfully",
        payload=combined,
    )

