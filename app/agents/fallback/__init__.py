"""
Offline fallback for session Q&A when question generation LLM fails: static question bank only.

Answer-evaluation placeholders live in ``session_qa_agent`` (not here).
"""

from app.agents.fallback.interview_questions import (
    FALLBACK_QUESTION_BANK,
    pick_fallback_question,
)

__all__ = [
    "FALLBACK_QUESTION_BANK",
    "pick_fallback_question",
]
