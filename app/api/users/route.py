"""Users API: readiness dashboard, etc."""

import uuid as uuid_pkg
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.users.schemas import ReadinessSummaryResponse, ReadinessTrendItem
from app.common.http_response_model import CommonResponse
from app.models import User
from app.api.users.service import (
    get_cv_and_gap,
    get_readiness_trend_data,
    get_recent_session_stats,
)
from app.services.readiness_aggregator import compute_combined_readiness

router = APIRouter()

LAST_N_SESSIONS = 5


@router.get(
    "/me/readiness",
    response_model=CommonResponse[dict],
    name="Get combined readiness",
    summary="Get combined readiness score (CV + sessions + gap) for current user.",
)
async def get_my_readiness(
    resume_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional resume ID for CV score and gap analysis.",
    ),
    job_posting_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional job posting ID for gap analysis (requires resume_id).",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns combined readiness score aggregating:
    - CV score (if resume_id provided and CV scoring enabled)
    - Average of last N session readiness scores
    - Gap penalty (if resume_id and job_posting_id provided)
    """
    cv_score, gap_severity = await get_cv_and_gap(
        db=db,
        current_user=current_user,
        resume_id=resume_id,
        job_posting_id=job_posting_id,
    )

    session_avg, _total, _with_scores, _dist = await get_recent_session_stats(
        db=db,
        current_user=current_user,
        last_n_sessions=LAST_N_SESSIONS,
    )

    combined, trend = compute_combined_readiness(
        cv_score=cv_score,
        session_avg=session_avg,
        gap_severity=gap_severity,
    )

    payload = {
        "combined_score": combined,
        "cv_score": cv_score,
        "session_avg": session_avg,
        "gap_severity": gap_severity,
        "trend": trend,
    }
    return CommonResponse(
        success=True,
        message="Readiness retrieved successfully",
        payload=payload,
    )


@router.get(
    "/me/readiness/trend",
    response_model=CommonResponse[List[ReadinessTrendItem]],
    name="Get readiness trend",
    summary="Get recent session readiness scores for the current user.",
)
async def get_my_readiness_trend(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of recent sessions to return.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a list of recent sessions with individual readiness scores and timestamps
    for plotting trends in the frontend.
    """
    data = await get_readiness_trend_data(
        db=db,
        user_id=current_user.id,
        limit=limit,
    )
    items = [ReadinessTrendItem(**item) for item in data]
    return CommonResponse(
        success=True,
        message="Readiness trend retrieved successfully",
        payload=items,
    )


@router.get(
    "/me/readiness/summary",
    response_model=CommonResponse[ReadinessSummaryResponse],
    name="Get readiness summary",
    summary="Get readiness summary and aggregates for the current user (dashboard).",
)
async def get_my_readiness_summary(
    resume_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional resume ID for CV score and gap analysis.",
    ),
    job_posting_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional job posting ID for gap analysis (requires resume_id).",
    ),
    last_n_sessions: int = Query(
        default=LAST_N_SESSIONS,
        ge=1,
        le=50,
        description="Number of recent sessions to consider for session_avg and difficulty distribution.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a dashboard-friendly readiness summary aggregating:
    - Combined readiness score and trend
    - CV score and gap severity (if resume/job IDs provided)
    - Session averages and counts
    - Difficulty distribution over recent sessions
    """
    cv_score, gap_severity = await get_cv_and_gap(
        db=db,
        current_user=current_user,
        resume_id=resume_id,
        job_posting_id=job_posting_id,
    )

    session_avg, session_count_total, session_count_with_scores, difficulty_distribution = (
        await get_recent_session_stats(
            db=db,
            current_user=current_user,
            last_n_sessions=last_n_sessions,
        )
    )

    combined, trend = compute_combined_readiness(
        cv_score=cv_score,
        session_avg=session_avg,
        gap_severity=gap_severity,
    )

    payload = ReadinessSummaryResponse(
        combined_score=combined,
        trend=trend,
        cv_score=cv_score,
        session_avg=session_avg,
        gap_severity=gap_severity,
        session_count_total=session_count_total,
        session_count_with_scores=session_count_with_scores,
        last_n_sessions=last_n_sessions,
        difficulty_distribution=difficulty_distribution,
    )
    return CommonResponse(
        success=True,
        message="Readiness summary retrieved successfully",
        payload=payload,
    )
