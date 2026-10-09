"""
Adaptive interview policy: role level from the job posting, question difficulty from recent
scores, and question-type balance. Pure functions; the session service feeds them messages.
"""

import re
from dataclasses import dataclass
from statistics import mean
from typing import Dict, List, Optional, Sequence

from app.agents.session_qa_agent import get_suggested_difficulty
from app.schemas.common import RoleLevel

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

# Average of the last ADAPT_WINDOW scores decides the next step.
ADAPT_WINDOW = 2
STEP_UP_AT = 80
STEP_DOWN_BELOW = 50

_INTERN_RE = re.compile(r"\b(intern|internship|trainee|placement|apprentice)\b")
# "staff" only with engineer: "Staff Accountant" is a junior accounting title.
_SENIOR_RE = re.compile(r"\b(senior|sr\.?|lead|principal|head of|architect|staff (?:\w+ )?engineer)\b")
_JUNIOR_RE = re.compile(r"\b(junior|jr\.?|graduate|entry[- ]level|associate)\b")
_YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|to)?\s*(?:\d{1,2})?\s*\+?\s*(?:years?|yrs?)")
SENIOR_MIN_YEARS = 5


def infer_role_level(job_entities: Optional[Dict[str, List[str]]]) -> Optional[str]:
    """Best-effort seniority from job title / experience / job type. None when unclear."""
    if not job_entities:
        return None
    parts: List[str] = []
    for key in ("JOB_TITLE", "EXPERIENCE_REQUIRED", "JOB_TYPE", "OCCUPATION", "EXPERIENCE"):
        values = job_entities.get(key) or []
        if isinstance(values, list):
            parts.extend(str(v) for v in values)
    text = " ".join(parts).lower()
    if not text.strip():
        return None
    if _INTERN_RE.search(text):
        return RoleLevel.INTERN.value
    if _SENIOR_RE.search(text):
        return RoleLevel.SSE.value
    years = [int(m.group(1)) for m in _YEARS_RE.finditer(text)]
    if years and min(years) >= SENIOR_MIN_YEARS:
        return RoleLevel.SSE.value
    if years or _JUNIOR_RE.search(text):
        return RoleLevel.ASE.value
    return None


@dataclass
class DifficultyChoice:
    difficulty: str
    reason: str  # "curve" | "step_up" | "step_down" | "hold"


def _step(level: str, delta: int) -> str:
    i = DIFFICULTY_LEVELS.index(level) + delta
    return DIFFICULTY_LEVELS[max(0, min(len(DIFFICULTY_LEVELS) - 1, i))]


def choose_difficulty(
    question_index: int,
    last_question_difficulty: Optional[str],
    recent_scores: Sequence[float],
) -> DifficultyChoice:
    """Next difficulty: position curve until there are scores, then adapt to performance."""
    if not recent_scores:
        return DifficultyChoice(get_suggested_difficulty(question_index), "curve")
    current = (
        last_question_difficulty
        if last_question_difficulty in DIFFICULTY_LEVELS
        else get_suggested_difficulty(question_index)
    )
    avg = mean(recent_scores[-ADAPT_WINDOW:])
    if avg >= STEP_UP_AT:
        return DifficultyChoice(_step(current, +1), "step_up")
    if avg < STEP_DOWN_BELOW:
        return DifficultyChoice(_step(current, -1), "step_down")
    return DifficultyChoice(current, "hold")


# Question-type balance: keep behavioral questions in the mix without forcing a type on
# every turn. system_design is left to the model (not relevant for every role).
BALANCE_AFTER = 3
BEHAVIORAL_LOOKBACK = 4
MAX_BEHAVIORAL_STREAK = 2


def choose_question_type(previous_types: Sequence[Optional[str]]) -> Optional[str]:
    """Requested type for the next question, or None to let the model choose."""
    if len(previous_types) < BALANCE_AFTER:
        return None
    if "behavioral" not in previous_types[-BEHAVIORAL_LOOKBACK:]:
        return "behavioral"
    recent = previous_types[-MAX_BEHAVIORAL_STREAK:]
    if len(recent) == MAX_BEHAVIORAL_STREAK and all(t == "behavioral" for t in recent):
        return "technical"
    return None
