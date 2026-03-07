"""Match API: skill-gap analysis between resume and job posting."""

import uuid as uuid_pkg

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.match.schemas import SkillGapAlert, SkillGapRequest, SkillGapResponse
from app.common.http_response_model import CommonResponse
from app.models import JobPosting, Resume, User
from app.services.skill_gap_service import analyze_skill_gap

router = APIRouter()


async def _get_own_resume(
    resume_id: uuid_pkg.UUID,
    current_user: User,
    db: AsyncSession,
) -> Resume:
    """Load resume by ID; raise 404 if not found or not owned."""
    resume = await db.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return resume


async def _get_own_job_posting(
    job_posting_id: uuid_pkg.UUID,
    current_user: User,
    db: AsyncSession,
) -> JobPosting:
    """Load job posting by ID; raise 404 if not found or not owned."""
    job = await db.get(JobPosting, job_posting_id)
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    return job


@router.post(
    "/skill-gap",
    response_model=CommonResponse[SkillGapResponse],
    name="Skill gap analysis",
    summary="Compare resume vs job posting; return missing skills, weak areas, suggestions, alerts.",
)
async def post_skill_gap(
    body: SkillGapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze the gap between a resume and a job posting. Returns missing skills,
    weak experience/education flags, actionable suggestions, and structured alerts.
    """
    try:
        rid = uuid_pkg.UUID(body.resume_id)
        jid = uuid_pkg.UUID(body.job_posting_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid resume_id or job_posting_id.")

    resume = await _get_own_resume(rid, current_user, db)
    job = await _get_own_job_posting(jid, current_user, db)

    result = analyze_skill_gap(
        resume_entities=resume.entities or {},
        job_entities=job.entities or {},
    )

    alerts = [
        SkillGapAlert(
            type=a["type"],
            message=a["message"],
            severity=a["severity"],
        )
        for a in result["alerts"]
    ]

    payload = SkillGapResponse(
        missing_skills=result["missing_skills"],
        weak_experience=result["weak_experience"],
        weak_experience_message=result.get("weak_experience_message"),
        weak_education=result["weak_education"],
        weak_education_message=result.get("weak_education_message"),
        suggestions=result["suggestions"],
        severity=result["severity"],
        alerts=alerts,
    )
    return CommonResponse(
        success=True,
        message="Skill gap analysis completed",
        payload=payload,
    )
