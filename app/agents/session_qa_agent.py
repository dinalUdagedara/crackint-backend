"""
Session Q&A agent: question generation and answer evaluation for interview prep.
Uses LLM with prompts from docs/SESSION_QA_PROMPTS.md.
"""

import json
import logging
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

# --- Question generation ---

QUESTION_SYSTEM_PROMPT = """You are an expert technical interviewer. Your task is to generate exactly one interview question for a practice session.

Context you will receive:
- Role level: INTERN, ASE, or SSE (adjust question depth and scope accordingly).
- Job posting entities: job title, company, required skills, experience, education, job type.
- Candidate resume entities: skills, occupation, education, experience.
- The list of questions and messages already exchanged in this session (do not repeat or rephrase those questions).

Rules:
- Output exactly one new question suitable for the given role level and aligned with the job requirements and the candidate's background.
- Prefer questions that let the candidate demonstrate relevant skills or experience from their resume where applicable.
- If question_type is specified (technical, behavioral, or system_design), generate that type; otherwise you may choose.
- Respond with a single JSON object with keys: "question" (string), optional "difficulty" (easy|medium|hard), optional "question_type" (technical|behavioral|system_design).
- Do not include any text outside the JSON object."""


class QuestionGenerationResult(BaseModel):
    """Structured result from question generation."""

    question: str = Field(..., description="The interview question text.")
    difficulty: Optional[str] = Field(
        default=None,
        description="easy, medium, or hard.",
    )
    question_type: Optional[str] = Field(
        default=None,
        description="technical, behavioral, or system_design.",
    )


def _is_session_qa_available() -> bool:
    """True if Session Q&A agent is enabled and API key is set."""
    return bool(
        getattr(settings, "SESSION_QA_AGENT_ENABLED", False)
        and getattr(settings, "OPENAI_API_KEY", None)
    )


def _strip_json_fence(content: str) -> str:
    """Remove markdown code fence if present."""
    content = (content or "").strip()
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    return content


async def generate_next_question(
    role_level: str,
    job_entities: Dict[str, List[str]],
    resume_entities: Dict[str, List[str]],
    previous_messages: List[Dict[str, Any]],
    question_type: Optional[str] = None,
) -> QuestionGenerationResult:
    """
    Call LLM to generate the next interview question.
    Raises ValueError if agent disabled/API key missing or LLM fails.
    """
    if not _is_session_qa_available():
        raise ValueError(
            "Session Q&A agent is disabled (SESSION_QA_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )

    job_json = json.dumps(job_entities, ensure_ascii=False, indent=2)
    resume_json = json.dumps(resume_entities, ensure_ascii=False, indent=2)
    messages_formatted = "\n".join(
        f"- [{m.get('sender', '?')}] ({m.get('type', '?')}): {m.get('content', '')[:200]}"
        for m in previous_messages[-30:]
    )
    if not messages_formatted.strip():
        messages_formatted = "(No previous messages yet.)"
    qtype_str = question_type or "(any)"

    user_content = f"""Role level: {role_level}

Job posting entities (key: list of values):
{job_json}

Candidate resume entities (key: list of values):
{resume_json}

Previous messages in this session (do not repeat these as questions):
{messages_formatted}

Requested question type (or leave empty to choose): {qtype_str}"""

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("Session Q&A: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    model = getattr(settings, "SESSION_QA_AGENT_MODEL", "gpt-4o-mini")
    temperature = getattr(settings, "SESSION_QA_AGENT_TEMPERATURE", 0.7)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")

        content = _strip_json_fence(content)
        parsed = json.loads(content)
        question = (parsed.get("question") or "").strip()
        if not question:
            raise ValueError("LLM response missing 'question' field.")

        return QuestionGenerationResult(
            question=question,
            difficulty=parsed.get("difficulty"),
            question_type=parsed.get("question_type"),
        )
    except json.JSONDecodeError as e:
        logger.warning("Session Q&A question gen: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from question generator.") from e
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.warning("Session Q&A question gen: LLM call failed: %s", e)
        raise ValueError("Question generation failed.") from e


# --- Answer evaluation ---

EVAL_SYSTEM_PROMPT = """You are an expert technical interviewer evaluating a candidate's answer in a practice session.

Your task: Given the question and the candidate's answer, produce:
1. Text feedback: 2–4 sentences covering strengths, areas for improvement, and one or two actionable suggestions.
2. A score from 0 to 100 (inclusive). Consider: depth of content, relevance to the question, clarity, structure (e.g. STAR for behavioral), and fit for the role level.
3. A short list of dimension tags (e.g. technical, communication, structure, relevance, clarity, behavioral) that best describe what your feedback addresses.

Role level (INTERN / ASE / SSE) is provided; calibrate expectations accordingly (e.g. INTERN: more lenient on depth; SSE: expect more leadership/system thinking).

Respond with a single JSON object with keys: "feedback" (string), "score" (integer 0–100), "dimension_tags" (array of strings). Do not include any text outside the JSON object."""


class AnswerEvaluationResult(BaseModel):
    """Structured result from answer evaluation."""

    feedback: str = Field(..., description="Text feedback for the candidate.")
    score: int = Field(..., ge=0, le=100, description="Score 0-100.")
    dimension_tags: List[str] = Field(
        default_factory=list,
        description="Tags such as technical, communication, structure.",
    )


async def evaluate_answer(
    question: str,
    answer: str,
    role_level: str,
    job_entities: Dict[str, List[str]],
    resume_entities: Dict[str, List[str]],
) -> AnswerEvaluationResult:
    """
    Call LLM to evaluate the candidate's answer.
    Raises ValueError if agent disabled/API key missing or LLM fails.
    """
    if not _is_session_qa_available():
        raise ValueError(
            "Session Q&A agent is disabled (SESSION_QA_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )

    job_json = json.dumps(job_entities, ensure_ascii=False, indent=2)
    resume_json = json.dumps(resume_entities, ensure_ascii=False, indent=2)

    user_content = f"""Role level: {role_level}

Question:
{question}

Candidate's answer:
{answer}

Job context (for relevance):
{job_json}

Candidate background (for relevance):
{resume_json}"""

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("Session Q&A: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    model = getattr(settings, "SESSION_QA_AGENT_MODEL", "gpt-4o-mini")
    temperature = getattr(settings, "SESSION_QA_AGENT_TEMPERATURE", 0.7)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EVAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")

        content = _strip_json_fence(content)
        parsed = json.loads(content)
        feedback = (parsed.get("feedback") or "").strip()
        if not feedback:
            raise ValueError("LLM response missing 'feedback' field.")

        raw_score = parsed.get("score")
        if raw_score is None:
            raise ValueError("LLM response missing 'score' field.")
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            score = 50
        score = max(0, min(100, score))

        tags = parsed.get("dimension_tags")
        if not isinstance(tags, list):
            tags = []
        dimension_tags = [str(t).strip() for t in tags if t]

        return AnswerEvaluationResult(
            feedback=feedback,
            score=score,
            dimension_tags=dimension_tags,
        )
    except json.JSONDecodeError as e:
        logger.warning("Session Q&A answer eval: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from answer evaluator.") from e
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.warning("Session Q&A answer eval: LLM call failed: %s", e)
        raise ValueError("Answer evaluation failed.") from e


# --- Session summary (strengths / areas_for_improvement) ---

SUMMARY_SYSTEM_PROMPT = """You are an expert technical interviewer summarizing a candidate's performance across several answer evaluations in a practice session.

Your task: Given a list of feedback items (each with text and optional dimension tags), produce a concise session-level summary:
1. "strengths": 2–4 bullet points or short sentences summarizing what the candidate did well across the feedback (e.g. clear structure, good technical depth, concrete examples).
2. "areas_for_improvement": 2–4 bullet points or short sentences summarizing the main areas to work on (e.g. add metrics, use STAR more consistently, clarify relevance to role).

Keep each section to a short paragraph or 2–4 bullets. Be specific but concise. Do not repeat the raw feedback verbatim; synthesize.

Respond with a single JSON object with keys: "strengths" (string), "areas_for_improvement" (string). Do not include any text outside the JSON object."""

# Max number of feedback items to send to the summarizer (to stay within context).
SUMMARY_MAX_FEEDBACK_ITEMS = 10


class SessionSummaryResult(BaseModel):
    """Structured result from session feedback summarization."""

    strengths: str = Field(
        default="",
        description="Session-level strengths summary.",
    )
    areas_for_improvement: str = Field(
        default="",
        description="Session-level areas for improvement summary.",
    )


async def summarize_session_feedback(
    role_level: str,
    feedback_items: List[Dict[str, Any]],
    job_entities: Optional[Dict[str, List[str]]] = None,
    resume_entities: Optional[Dict[str, List[str]]] = None,
) -> SessionSummaryResult:
    """
    Call LLM to summarize feedback across the session into strengths and areas_for_improvement.
    feedback_items: list of {"content": str, "meta": dict} (e.g. Message.content and Message.meta).
    Raises ValueError if agent disabled/API key missing or LLM fails.
    """
    if not _is_session_qa_available():
        raise ValueError(
            "Session Q&A agent is disabled (SESSION_QA_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )

    items = feedback_items[-SUMMARY_MAX_FEEDBACK_ITEMS:]
    feedback_lines = []
    for i, item in enumerate(items, 1):
        content = (item.get("content") or "").strip()
        meta = item.get("meta") or {}
        tags = meta.get("dimension_tags")
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        elif not isinstance(tags, list):
            tags = []
        tags_str = ", ".join(tags) if tags else "—"
        feedback_lines.append(f"{i}. [tags: {tags_str}]\n   {content[:500]}")

    feedback_formatted = "\n\n".join(feedback_lines) if feedback_lines else "(No feedback yet.)"
    job_entities = job_entities or {}
    resume_entities = resume_entities or {}
    job_json = json.dumps(job_entities, ensure_ascii=False, indent=2)
    resume_json = json.dumps(resume_entities, ensure_ascii=False, indent=2)

    user_content = f"""Role level: {role_level}

Recent feedback from this session (text + dimension tags):
{feedback_formatted}

Job context (optional):
{job_json}

Candidate background (optional):
{resume_json}

Produce a short session-level summary as JSON: "strengths", "areas_for_improvement"."""

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("Session Q&A: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    model = getattr(settings, "SESSION_QA_AGENT_MODEL", "gpt-4o-mini")
    temperature = getattr(settings, "SESSION_QA_AGENT_TEMPERATURE", 0.7)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")

        content = _strip_json_fence(content)
        parsed = json.loads(content)
        strengths = (parsed.get("strengths") or "").strip()
        areas = (parsed.get("areas_for_improvement") or "").strip()

        return SessionSummaryResult(
            strengths=strengths,
            areas_for_improvement=areas,
        )
    except json.JSONDecodeError as e:
        logger.warning("Session Q&A summary: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from session summarizer.") from e
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.warning("Session Q&A summary: LLM call failed: %s", e)
        raise ValueError("Session summarization failed.") from e


# --- Session title (human-friendly chat name) ---

TITLE_SYSTEM_PROMPT = """You are an assistant that creates short, human-friendly titles for interview prep chat sessions.

You will receive:
- Role level (INTERN / ASE / SSE / OTHER)
- Job posting entities (job title, company, location, skills, etc.)
- Candidate resume entities (skills, occupation, etc.)
- The most recent interview question asked in this session.

Your task: Produce a concise title (ideally <= 60 characters) that would help the user recognize this session in a list.
Examples: "ASE Backend – Python role at Example Corp", "Behavioral practice – debugging production issues".

Rules:
- The title must be a single short text string (no newlines).
- Do not include quotes, markdown, or surrounding punctuation.
- If company or job title are missing, fall back to role level and question theme.
- Respond with a single JSON object: { "title": "..." } and nothing else."""


class SessionTitleResult(BaseModel):
    """Structured result from session title generation."""

    title: str = Field(
        default="",
        description="Short, human-friendly session title.",
    )


async def generate_session_title(
    role_level: str,
    job_entities: Optional[Dict[str, List[str]]] = None,
    resume_entities: Optional[Dict[str, List[str]]] = None,
    last_question: Optional[str] = None,
) -> SessionTitleResult:
    """
    Call LLM to generate a concise title for a prep session.
    Intended to be called once per session when the user starts chatting.
    """
    if not _is_session_qa_available():
        raise ValueError(
            "Session Q&A agent is disabled (SESSION_QA_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )

    job_entities = job_entities or {}
    resume_entities = resume_entities or {}
    job_json = json.dumps(job_entities, ensure_ascii=False, indent=2)
    resume_json = json.dumps(resume_entities, ensure_ascii=False, indent=2)
    question_text = (last_question or "").strip() or "(no question text available)"

    user_content = f"""Role level: {role_level}

Job posting entities (optional):
{job_json}

Candidate resume entities (optional):
{resume_json}

Most recent question in this session:
{question_text}

Return a single JSON object with key "title" containing a short, human-friendly name for this session."""

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("Session Q&A: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    model = getattr(settings, "SESSION_QA_AGENT_MODEL", "gpt-4o-mini")
    temperature = getattr(settings, "SESSION_QA_AGENT_TEMPERATURE", 0.5)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")

        content = _strip_json_fence(content)
        parsed = json.loads(content)
        title = (parsed.get("title") or "").strip()
        if not title:
            raise ValueError("LLM response missing 'title' field.")

        return SessionTitleResult(title=title)
    except json.JSONDecodeError as e:
        logger.warning("Session Q&A title: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from session title generator.") from e
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.warning("Session Q&A title: LLM call failed: %s", e)
        raise ValueError("Session title generation failed.") from e

