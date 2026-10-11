"""
Deadline-aware prep plan for a job posting: one task per day until the interview (or the
application deadline), built from skill gaps, weak topics and recent scores.

Computed on request (never stored), so it follows new scores, analyses and date changes.
Dates are calendar dates in server-local time, like the sessions' created_at.
"""

import uuid as uuid_pkg
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobPosting, Message, PrepSession, Resume, ResumeJobAnalysis
from app.services.skill_gap_service import analyze_skill_gap
from app.services.topic_mastery import list_mastery, status_of

MAX_PLAN_DAYS = 14
MAX_GAP_SKILLS = 4
MAX_WEAK_TOPICS = 3
BEHAVIORAL_EVERY_N_DAYS = 3
LOW_SCORE = 60
BEHAVIORAL_TOPIC = "behavioral stories (STAR)"


@dataclass
class PlanTask:
    date: date
    day_index: int
    kind: str  # skill_gap | weak_topic | behavioral | practice | mock_interview | day_of | deadline
    title: str
    description: str
    minutes: int
    focus_topics: List[str] = field(default_factory=list)
    mode: str = "TARGETED"
    done: bool = False
    is_today: bool = False


def _interleave(a: Sequence[str], b: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for i in range(max(len(a), len(b))):
        for seq in (a, b):
            if i < len(seq) and seq[i].strip().lower() not in seen:
                seen.add(seq[i].strip().lower())
                out.append(seq[i].strip())
    return out


def build_plan(
    today: date,
    target_date: date,
    target_type: str,
    missing_skills: Sequence[str],
    weak_topics: Sequence[str],
    avg_score: Optional[float],
    practiced_dates: Set[date],
) -> List[PlanTask]:
    """Pure planning function (see module docstring). Empty when the target date has passed."""
    days_left = (target_date - today).days
    if days_left < 0:
        return []
    prep_days = min(days_left, MAX_PLAN_DAYS)
    minutes = 30 if avg_score is None or avg_score < LOW_SCORE else 20
    gap_set = {s.lower() for s in missing_skills}
    queue = _interleave(list(missing_skills)[:MAX_GAP_SKILLS], list(weak_topics)[:MAX_WEAK_TOPICS])

    tasks: List[PlanTask] = []
    drill = 0
    for i in range(prep_days):
        day = date.fromordinal(today.toordinal() + i)
        is_last_prep_day = i == prep_days - 1
        if is_last_prep_day and target_type == "interview" and prep_days >= 2:
            task = PlanTask(day, i + 1, "mock_interview", "Full mock interview",
                            "A complete practice round for this role. End the session to get your report.",
                            45, [], "TARGETED")
        elif (i + 1) % BEHAVIORAL_EVERY_N_DAYS == 0:
            task = PlanTask(day, i + 1, "behavioral", "Behavioral stories (STAR)",
                            "Practice telling 2-3 stories with a clear Situation, Task, Action and Result.",
                            minutes, [BEHAVIORAL_TOPIC], "TARGETED")
        elif queue:
            topic = queue[drill % len(queue)]
            drill += 1
            if topic.lower() in gap_set:
                task = PlanTask(day, i + 1, "skill_gap", f"Close the gap: {topic}",
                                "The job asks for this and your CV doesn't show it yet. Drill questions on it.",
                                minutes, [topic], "TARGETED")
            else:
                task = PlanTask(day, i + 1, "weak_topic", f"Revisit: {topic}",
                                "You scored low on this before. Practice it until it sticks.",
                                minutes, [topic], "TARGETED")
        else:
            task = PlanTask(day, i + 1, "practice", "Targeted practice",
                            "A short practice session for this role.", minutes, [], "TARGETED")
        tasks.append(task)

    if target_type == "interview":
        tasks.append(PlanTask(target_date, prep_days + 1, "day_of", "Interview day: quick warm-up",
                              "Two or three easy questions to warm up. Review your report's strengths.",
                              10, [], "QUICK_PRACTICE"))
    else:
        tasks.append(PlanTask(target_date, prep_days + 1, "deadline", "Application deadline",
                              "Finalize your CV and cover letter and submit the application.",
                              15, [], "TARGETED"))

    for t in tasks:
        t.is_today = t.date == today
        t.done = t.date <= today and t.date in practiced_dates and t.kind != "deadline"
    return tasks


def _local_date(dt: datetime) -> date:
    """Naive UTC (job dates) -> server-local calendar date."""
    return dt.replace(tzinfo=timezone.utc).astimezone().date()


def plan_target(job: JobPosting, now_utc: datetime) -> Optional[tuple[datetime, str]]:
    """Upcoming interview if set, else the upcoming application deadline."""
    for value, kind in ((job.interview_at, "interview"), (job.deadline, "deadline")):
        if value is not None:
            naive = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
            if naive.date() >= now_utc.date():
                return naive, kind
    return None


@dataclass
class PlanInputs:
    resume_id: Optional[uuid_pkg.UUID]
    missing_skills: List[str]
    weak_topics: List[str]
    avg_score: Optional[float]
    practiced_dates: Set[date]


async def gather_inputs(db: AsyncSession, user_id: uuid_pkg.UUID, job: JobPosting) -> PlanInputs:
    # Skill gaps: latest stored analysis for this job, else a quick rule-based one with the latest resume.
    analysis = (
        await db.execute(
            select(ResumeJobAnalysis, Resume.id)
            .join(Resume, Resume.id == ResumeJobAnalysis.resume_id)
            .where(ResumeJobAnalysis.job_posting_id == job.id, Resume.user_id == user_id)
            .order_by(ResumeJobAnalysis.analyzed_at.desc())
            .limit(1)
        )
    ).first()
    if analysis is not None:
        row, resume_id = analysis
        missing = list((row.result or {}).get("missing_skills") or [])
    else:
        resume = (
            await db.execute(
                select(Resume).where(Resume.user_id == user_id).order_by(Resume.updated_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        resume_id = resume.id if resume else None
        missing = (
            list(analyze_skill_gap(resume_entities=resume.entities or {}, job_entities=job.entities or {}).get("missing_skills") or [])
            if resume
            else []
        )

    weak = [r.topic for r in await list_mastery(db, user_id) if status_of(r) != "mastered"]

    sessions = list(
        (
            await db.execute(
                select(PrepSession).where(PrepSession.user_id == user_id, PrepSession.job_posting_id == job.id)
            )
        ).scalars().all()
    )
    session_ids = [s.id for s in sessions]
    scores: List[float] = []
    practiced: Set[date] = set()
    if session_ids:
        feedback = (
            await db.execute(
                select(Message).where(Message.session_id.in_(session_ids), Message.type == "FEEDBACK")
            )
        ).scalars().all()
        for m in feedback:
            raw = (m.meta or {}).get("score")
            if raw is None:
                continue
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                continue
            practiced.add(m.created_at.date())
    return PlanInputs(
        resume_id=resume_id,
        missing_skills=[str(s) for s in missing if str(s).strip()],
        weak_topics=weak,
        avg_score=round(sum(scores[-20:]) / len(scores[-20:]), 1) if scores else None,
        practiced_dates=practiced,
    )


async def get_prep_plan(db: AsyncSession, user_id: uuid_pkg.UUID, job: JobPosting) -> Dict:
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    target = plan_target(job, now_utc)
    inputs = await gather_inputs(db, user_id, job)
    base = {
        "job_posting_id": job.id,
        "resume_id": inputs.resume_id,
        "missing_skills": inputs.missing_skills[:MAX_GAP_SKILLS],
        "weak_topics": inputs.weak_topics[:MAX_WEAK_TOPICS],
        "avg_score": inputs.avg_score,
    }
    if target is None:
        return {**base, "target_date": None, "target_type": None, "days_left": None, "tasks": []}
    target_dt, target_type = target
    today = datetime.now().date()
    target_date = _local_date(target_dt)
    tasks = build_plan(
        today, target_date, target_type,
        inputs.missing_skills, inputs.weak_topics, inputs.avg_score, inputs.practiced_dates,
    )
    return {
        **base,
        "target_date": target_date,
        "target_type": target_type,
        "days_left": (target_date - today).days,
        "tasks": [t.__dict__ for t in tasks],
    }
