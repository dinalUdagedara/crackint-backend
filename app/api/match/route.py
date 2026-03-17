"""Match API: skill-gap analysis between resume and job posting."""

import logging
from datetime import datetime
import uuid as uuid_pkg

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.resume_job_fit_agent import analyze_resume_job_fit
from app.api.deps import get_current_user, get_db
from app.api.match.schemas import (
    LocationSuitability,
    ResumeJobFitAnalysis,
    SkillGapAlert,
    SkillGapRequest,
    SkillGapResponse,
)
from app.common.http_response_model import CommonResponse
from app.models import JobPosting, Resume, ResumeJobAnalysis, User
from app.services.skill_gap_service import analyze_location_suitability, analyze_skill_gap

logger = logging.getLogger(__name__)

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


@router.get(
    "/skill-gap",
    response_model=CommonResponse[SkillGapResponse],
    name="Get stored skill-gap analysis",
    summary="Return the last saved analysis for this resume+job pair (404 if none).",
)
async def get_skill_gap(
    resume_id: uuid_pkg.UUID = Query(..., description="Resume UUID."),
    job_posting_id: uuid_pkg.UUID = Query(..., description="Job posting UUID."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the stored skill-gap (and optional LLM fit) analysis for this resume and job.
    Run POST /match/skill-gap first to compute and save an analysis.
    """
    await _get_own_resume(resume_id, current_user, db)
    await _get_own_job_posting(job_posting_id, current_user, db)

    existing = await db.execute(
        select(ResumeJobAnalysis).where(
            ResumeJobAnalysis.resume_id == resume_id,
            ResumeJobAnalysis.job_posting_id == job_posting_id,
        ).limit(1)
    )
    row = existing.scalars().one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No analysis found for this resume and job. Run POST /match/skill-gap to generate one.",
        )

    payload = SkillGapResponse.model_validate(
        {**row.result, "analyzed_at": row.analyzed_at}
    )
    return CommonResponse(
        success=True,
        message="Stored analysis retrieved",
        payload=payload,
    )


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

    # Candidate location: request body (profile/CV) or first resume LOCATION entity if present
    candidate_location = body.candidate_location
    if not candidate_location and resume.entities:
        loc_entities = (resume.entities or {}).get("LOCATION", [])
        if loc_entities and isinstance(loc_entities[0], str):
            candidate_location = loc_entities[0]

    # Job location display for fit agent and fallback
    job_entities = job.entities or {}
    job_loc_list = job_entities.get("LOCATION", []) or []
    job_location_display = (job.location or "").strip()
    if not job_location_display and job_loc_list:
        job_location_display = ", ".join(str(x).strip() for x in job_loc_list if x)

    llm_fit_analysis: ResumeJobFitAnalysis | None = None
    location_suitability: LocationSuitability
    loc_alert: SkillGapAlert | None = None
    resume_text = (resume.raw_text or "").strip()
    job_text = (job.raw_text or "").strip()

    if resume_text and job_text:
        try:
            fit_result = await analyze_resume_job_fit(
                resume_text,
                job_text,
                job_location_display=job_location_display or None,
                candidate_location=candidate_location,
            )
            llm_fit_analysis = ResumeJobFitAnalysis(
                fit_score=fit_result.fit_score,
                summary=fit_result.summary,
                tailored_suggestions=fit_result.tailored_suggestions,
            )
            if fit_result.location_suitability:
                location_suitability = LocationSuitability(**fit_result.location_suitability)
                if fit_result.location_alert:
                    loc_alert = SkillGapAlert(
                        type=fit_result.location_alert["type"],
                        message=fit_result.location_alert["message"],
                        severity=fit_result.location_alert["severity"],
                    )
            else:
                loc_payload, loc_alert_dict = analyze_location_suitability(
                    job_location_str=job.location,
                    job_entities=job_entities,
                    candidate_location=candidate_location,
                )
                location_suitability = LocationSuitability(**loc_payload)
                if loc_alert_dict:
                    loc_alert = SkillGapAlert(
                        type=loc_alert_dict["type"],
                        message=loc_alert_dict["message"],
                        severity=loc_alert_dict["severity"],
                    )
        except ValueError as e:
            logger.info("Match skill-gap: LLM fit analysis skipped or failed: %s", e)
            loc_payload, loc_alert_dict = analyze_location_suitability(
                job_location_str=job.location,
                job_entities=job_entities,
                candidate_location=candidate_location,
            )
            location_suitability = LocationSuitability(**loc_payload)
            if loc_alert_dict:
                loc_alert = SkillGapAlert(
                    type=loc_alert_dict["type"],
                    message=loc_alert_dict["message"],
                    severity=loc_alert_dict["severity"],
                )
    else:
        loc_payload, loc_alert_dict = analyze_location_suitability(
            job_location_str=job.location,
            job_entities=job_entities,
            candidate_location=candidate_location,
        )
        location_suitability = LocationSuitability(**loc_payload)
        if loc_alert_dict:
            loc_alert = SkillGapAlert(
                type=loc_alert_dict["type"],
                message=loc_alert_dict["message"],
                severity=loc_alert_dict["severity"],
            )

    alerts = [
        SkillGapAlert(
            type=a["type"],
            message=a["message"],
            severity=a["severity"],
        )
        for a in result["alerts"]
    ]
    if loc_alert:
        alerts.append(loc_alert)

    analyzed_at = datetime.now()
    payload = SkillGapResponse(
        missing_skills=result["missing_skills"],
        weak_experience=result["weak_experience"],
        weak_experience_message=result.get("weak_experience_message"),
        weak_education=result["weak_education"],
        weak_education_message=result.get("weak_education_message"),
        suggestions=result["suggestions"],
        severity=result["severity"],
        alerts=alerts,
        llm_fit_analysis=llm_fit_analysis,
        location_suitability=location_suitability,
        analyzed_at=analyzed_at,
    )

    # Persist: upsert ResumeJobAnalysis for this resume+job pair
    result_dict = payload.model_dump(mode="json", exclude={"analyzed_at"})
    existing = await db.execute(
        select(ResumeJobAnalysis).where(
            ResumeJobAnalysis.resume_id == rid,
            ResumeJobAnalysis.job_posting_id == jid,
        ).limit(1)
    )
    row = existing.scalars().one_or_none()
    if row:
        row.result = result_dict
        row.analyzed_at = analyzed_at
        db.add(row)
    else:
        db.add(
            ResumeJobAnalysis(
                resume_id=rid,
                job_posting_id=jid,
                result=result_dict,
                analyzed_at=analyzed_at,
            )
        )
    await db.commit()

    return CommonResponse(
        success=True,
        message="Skill gap analysis completed",
        payload=payload,
    )
