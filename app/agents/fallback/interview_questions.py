"""
Static fallback interview questions when the LLM is unavailable or returns invalid output.
Generic, domain-agnostic prompts — expand or edit FALLBACK_QUESTION_BANK as needed.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Each entry: question text + optional difficulty / type for filtering (matches session QA conventions).
FALLBACK_QUESTION_BANK: List[Dict[str, str]] = [
    # Behavioral — easy
    {
        "question": "Tell me about yourself and what draws you to this kind of role.",
        "difficulty": "easy",
        "question_type": "behavioral",
    },
    {
        "question": "Describe a time you worked with someone whose style was very different from yours. How did you handle it?",
        "difficulty": "easy",
        "question_type": "behavioral",
    },
    {
        "question": "What is a professional accomplishment you are proud of, and what did you learn from it?",
        "difficulty": "easy",
        "question_type": "behavioral",
    },
    {
        "question": "Tell me about a time you missed a deadline or made a mistake. What happened and what did you do next?",
        "difficulty": "easy",
        "question_type": "behavioral",
    },
    # Behavioral — medium
    {
        "question": "Describe a situation where you had to prioritize competing tasks or stakeholders. How did you decide?",
        "difficulty": "medium",
        "question_type": "behavioral",
    },
    {
        "question": "Tell me about a time you received difficult feedback. How did you respond?",
        "difficulty": "medium",
        "question_type": "behavioral",
    },
    {
        "question": "Give an example of how you have improved a process or workflow in a past role or project.",
        "difficulty": "medium",
        "question_type": "behavioral",
    },
    {
        "question": "Describe a conflict or disagreement at work or school and how you worked toward a resolution.",
        "difficulty": "medium",
        "question_type": "behavioral",
    },
    # Behavioral — hard
    {
        "question": "Tell me about a time you had to lead or influence others without formal authority. What was the outcome?",
        "difficulty": "hard",
        "question_type": "behavioral",
    },
    {
        "question": "Describe a high-stakes decision you contributed to. What information did you need and what trade-offs did you consider?",
        "difficulty": "hard",
        "question_type": "behavioral",
    },
    # Technical (generic / domain-agnostic)
    {
        "question": "Walk me through how you would approach learning a new tool or technology you need for a project.",
        "difficulty": "easy",
        "question_type": "technical",
    },
    {
        "question": "Explain a technical concept you know well to someone non-technical, as you would in an interview.",
        "difficulty": "easy",
        "question_type": "technical",
    },
    {
        "question": "Describe how you test or validate your work before you consider it done.",
        "difficulty": "medium",
        "question_type": "technical",
    },
    {
        "question": "Tell me about a technical problem you debugged or solved. How did you narrow down the cause?",
        "difficulty": "medium",
        "question_type": "technical",
    },
    {
        "question": "How do you handle reviewing or critiquing a teammate's work constructively?",
        "difficulty": "medium",
        "question_type": "technical",
    },
    {
        "question": "Describe a time you had to simplify a complex problem. What was your approach?",
        "difficulty": "hard",
        "question_type": "technical",
    },
    # System design (light / generic)
    {
        "question": "How would you break down a large ambiguous project into manageable pieces?",
        "difficulty": "medium",
        "question_type": "system_design",
    },
    {
        "question": "What factors would you consider when designing something that needs to be reliable and easy to change later?",
        "difficulty": "medium",
        "question_type": "system_design",
    },
    {
        "question": "Describe how you would approach scaling a solution if usage grew much faster than expected.",
        "difficulty": "hard",
        "question_type": "system_design",
    },
    # Motivation / role fit (any type)
    {
        "question": "Why are you interested in this role, and what do you hope to contribute in your first few months?",
        "difficulty": "easy",
        "question_type": "behavioral",
    },
    {
        "question": "What kind of environment helps you do your best work?",
        "difficulty": "easy",
        "question_type": "behavioral",
    },
]

_LAST_RESORT_QUESTION = (
    "Describe a recent project or experience that best represents how you work, "
    "and what you would do differently if you did it again."
)


def _normalize_for_dedup(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _texts_overlap(candidate: str, previous: str) -> bool:
    """True if candidate is duplicate or strong substring overlap with a prior question."""
    a = _normalize_for_dedup(candidate)
    b = _normalize_for_dedup(previous)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < 24:
        return a == b
    return shorter in longer


def _collect_previous_question_texts(previous_messages: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for m in previous_messages:
        if (m.get("type") or "").upper() == "QUESTION":
            c = (m.get("content") or "").strip()
            if c:
                out.append(c)
    return out


def _conflicts_with_history(candidate: str, previous_questions: List[str]) -> bool:
    for pq in previous_questions:
        if _texts_overlap(candidate, pq):
            return True
    return False


def pick_fallback_question(
    previous_messages: List[Dict[str, Any]],
    question_index: int = 0,
    question_type: Optional[str] = None,
    suggested_difficulty: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Choose a static question not overlapping prior QUESTION messages in this session.
    Uses question_type and suggested_difficulty when possible to pick a reasonable match.
    Returns (question, difficulty, question_type) for wrapping in QuestionGenerationResult.
    """
    prev_qs = _collect_previous_question_texts(previous_messages)
    qtype = (question_type or "").strip().lower() or None
    diff = (suggested_difficulty or "").strip().lower() or None
    if diff not in ("easy", "medium", "hard"):
        diff = None

    def pool_for_type() -> List[Dict[str, str]]:
        if not qtype:
            return list(FALLBACK_QUESTION_BANK)
        typed = [e for e in FALLBACK_QUESTION_BANK if e.get("question_type", "").lower() == qtype]
        return typed if typed else list(FALLBACK_QUESTION_BANK)

    pool = pool_for_type()

    # Prefer entries matching suggested_difficulty first, then the rest.
    if diff:
        preferred = [e for e in pool if e.get("difficulty", "").lower() == diff]
        rest = [e for e in pool if e.get("difficulty", "").lower() != diff]
        ordered = preferred + rest
    else:
        ordered = pool

    n = len(ordered)
    start = (question_index * 7 + n) % n if n else 0

    for i in range(n):
        entry = ordered[(start + i) % n]
        q = (entry.get("question") or "").strip()
        if not q:
            continue
        if not _conflicts_with_history(q, prev_qs):
            return (
                q,
                entry.get("difficulty"),
                entry.get("question_type"),
            )

    if not _conflicts_with_history(_LAST_RESORT_QUESTION, prev_qs):
        return (_LAST_RESORT_QUESTION, diff or "medium", qtype or "behavioral")

    # Extremely long session: minimal variant so content still differs slightly from history.
    suffix = " (Consider a different example than in your earlier answers.)"
    logger.warning("Fallback question bank exhausted overlaps; appending hint to last-resort prompt.")
    return (_LAST_RESORT_QUESTION + suffix, diff or "medium", qtype or "behavioral")
