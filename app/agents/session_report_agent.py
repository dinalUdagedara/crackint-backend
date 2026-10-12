"""
End-of-session report agent: model answers, STAR breakdowns for behavioral answers, topics,
strengths and weak topics for a completed prep session.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.session_qa_agent import _is_session_qa_available, _strip_json_fence
from app.config import settings
from app.services.llm import chat_completion, get_client

logger = logging.getLogger(__name__)

# Keep the prompt bounded: last N answered questions, answers truncated.
REPORT_MAX_ITEMS = 15
REPORT_MAX_ANSWER_CHARS = 1200

REPORT_SYSTEM_PROMPT = """You are an expert interviewer writing the end-of-session report for a candidate's practice interview.

For each answered question you get: index, question, question type, the candidate's answer, the score (0-100) and the feedback already given.

Return a single JSON object:
{
  "items": [
    {
      "index": <same index>,
      "topic": "<2-4 word topic the question tested, e.g. 'SQL indexing', 'conflict resolution'>",
      "model_answer": "<a strong, concise answer (4-7 sentences) at the given role level, written as the candidate would say it>",
      "star": null or {"situation": bool, "task": bool, "action": bool, "result": bool, "note": "<one sentence on what was missing or strong>"}
    }
  ],
  "strengths": ["<up to 3 short strengths, second person>"],
  "weak_topics": ["<up to 3 short topic names to practice next, most important first>"],
  "summary": "<2-3 sentences addressed to the candidate (use 'you')>"
}

Rules:
- Include "star" only for behavioral questions (null otherwise). Mark each STAR part true only if the answer clearly contains it.
- weak_topics are topics (e.g. "system design trade-offs"), not advice. Base them on low scores and the feedback.
- Calibrate model answers to the role level (INTERN / ASE / SSE). Do not invent company-specific facts about the candidate.
- Output JSON only."""


class StarBreakdown(BaseModel):
    situation: bool = False
    task: bool = False
    action: bool = False
    result: bool = False
    note: Optional[str] = None


class ReportItemInsight(BaseModel):
    index: int
    topic: Optional[str] = None
    model_answer: Optional[str] = None
    star: Optional[StarBreakdown] = None


class SessionReportInsights(BaseModel):
    items: List[ReportItemInsight] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weak_topics: List[str] = Field(default_factory=list)
    summary: Optional[str] = None


def _clean_list(value: Any, limit: int = 3) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def parse_report_insights(content: Optional[str]) -> SessionReportInsights:
    """Parse the model's JSON; raises ValueError if it is not usable."""
    try:
        parsed = json.loads(_strip_json_fence((content or "").strip()))
    except json.JSONDecodeError as e:
        raise ValueError("Invalid JSON from session report agent.") from e
    if not isinstance(parsed, dict):
        raise ValueError("Session report agent returned a non-object.")

    items: List[ReportItemInsight] = []
    for raw in parsed.get("items") or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("index"), int):
            continue
        star = raw.get("star")
        items.append(
            ReportItemInsight(
                index=raw["index"],
                topic=(str(raw.get("topic")).strip() or None) if raw.get("topic") else None,
                model_answer=(str(raw.get("model_answer")).strip() or None) if raw.get("model_answer") else None,
                star=StarBreakdown(**{k: star.get(k) for k in ("situation", "task", "action", "result", "note") if k in star})
                if isinstance(star, dict)
                else None,
            )
        )
    summary = parsed.get("summary")
    return SessionReportInsights(
        items=items,
        strengths=_clean_list(parsed.get("strengths")),
        weak_topics=_clean_list(parsed.get("weak_topics")),
        summary=str(summary).strip() if summary else None,
    )


async def generate_session_report(
    role_level: str,
    job_entities: Dict[str, List[str]],
    answered: List[Dict[str, Any]],
) -> SessionReportInsights:
    """
    answered: [{"index", "question", "question_type", "answer", "score", "feedback"}] in session order.
    Raises ValueError if the agent is disabled or the LLM fails (caller falls back to a basic report).
    """
    if not _is_session_qa_available():
        raise ValueError(
            "Session Q&A agent is disabled (SESSION_QA_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )
    try:
        get_client()
    except Exception as e:
        raise ValueError("OpenAI client unavailable.") from e

    lines = []
    for item in answered[-REPORT_MAX_ITEMS:]:
        lines.append(
            json.dumps(
                {
                    "index": item["index"],
                    "question": item["question"],
                    "question_type": item.get("question_type"),
                    "answer": (item.get("answer") or "")[:REPORT_MAX_ANSWER_CHARS],
                    "score": item.get("score"),
                    "feedback": item.get("feedback"),
                },
                ensure_ascii=False,
            )
        )
    user_content = (
        f"Role level: {role_level}\n\n"
        f"Job posting entities:\n{json.dumps(job_entities or {}, ensure_ascii=False)}\n\n"
        "Answered questions (one JSON object per line):\n" + "\n".join(lines)
    )
    try:
        response = await chat_completion(
            agent="session_qa.report",
            model=getattr(settings, "SESSION_QA_AGENT_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.warning("Session report: LLM call failed: %s", e)
        raise ValueError("Session report generation failed.") from e
    return parse_report_insights(response.choices[0].message.content)
