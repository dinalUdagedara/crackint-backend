"""
Session Q&A agent: question generation and answer evaluation for interview prep.
Uses LLM with prompts from docs/SESSION_QA_PROMPTS.md.
"""

import json
import logging
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

from app.agents.fallback import pick_fallback_question
from app.config import settings

logger = logging.getLogger(__name__)

# --- Question generation (v2: domain-agnostic role level + difficulty curve) ---

# Difficulty curve: map 0-based question index in session to suggested difficulty.
# Sessions progress from easier to harder. Thresholds are tunable.
DIFFICULTY_CURVE_EASY_UNTIL = 2   # indices 0, 1 -> easy
DIFFICULTY_CURVE_MEDIUM_UNTIL = 5  # indices 2, 3, 4 -> medium; 5+ -> hard


def get_suggested_difficulty(question_index: int) -> str:
    """Return suggested difficulty for the next question based on position in session (0-based)."""
    if question_index < DIFFICULTY_CURVE_EASY_UNTIL:
        return "easy"
    if question_index < DIFFICULTY_CURVE_MEDIUM_UNTIL:
        return "medium"
    return "hard"


QUESTION_SYSTEM_PROMPT = """You are an expert interviewer. Your task is to generate exactly one interview question for a practice session. The job can be in any field (software, finance, marketing, operations, data, design, etc.); the job and resume entities define the domain and question type. Role level only sets depth and expectations.

Role level (generic seniority; apply to any industry):
- INTERN (entry-level): Learning mindset, foundational knowledge, willingness to grow. Ask questions appropriate for someone early in their career in this field. Simpler depth; focus on basics and learning experiences.
- ASE (mid-level): Ownership of deliverables, concrete examples with impact, decisions within a given scope. Ask questions for someone who can run projects or processes independently in this role.
- SSE (senior): Broader scope, leadership, mentoring, strategy, trade-offs. Ask questions for someone leading or influencing outcomes beyond their immediate work.

Context you will receive:
- Role level: INTERN, ASE, SSE, or OTHER (use the definitions above for depth and scope).
- Job posting entities: job title, company, required skills, experience, education, job type (these define the domain and what to ask about).
- Candidate resume entities: skills, occupation, education, experience.
- The list of questions and messages already exchanged in this session (do not repeat or rephrase those questions).
- Optional: suggested difficulty for this question and position in session (session should progress from easier to harder).

Rules:
- Output exactly one new question suitable for the given role level and aligned with the job requirements and the candidate's background. The domain (e.g. technical, behavioral, process design) comes from the job and resume; role level only adjusts how deep or broad the question is.
- Prefer questions that let the candidate demonstrate relevant skills or experience from their resume where applicable.
- If question_type is specified (technical, behavioral, or system_design), generate that type; otherwise you may choose based on the job.
- If a suggested difficulty is provided, prefer that difficulty (easy / medium / hard) so the session progresses from easier to harder.
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
    question_index: int = 0,
    suggested_difficulty: Optional[str] = None,
) -> QuestionGenerationResult:
    """
    Call LLM to generate the next interview question.
    question_index: 0-based count of QUESTION messages already in the session (for difficulty curve).
    suggested_difficulty: preferred difficulty for this position (easy/medium/hard); session progresses easier to harder.
    If the LLM is unavailable or returns invalid output, uses a static fallback bank (see app.agents.fallback).
    Raises ValueError only if Session Q&A is disabled (no API key / agent off).
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

    difficulty_line = ""
    if suggested_difficulty:
        difficulty_line = f"\nThis is question number {question_index + 1} in this session. Prefer difficulty: {suggested_difficulty}. The session should progress from easier to harder.\n"

    user_content = f"""Role level: {role_level}
{difficulty_line}
Job posting entities (key: list of values):
{job_json}

Candidate resume entities (key: list of values):
{resume_json}

Previous messages in this session (do not repeat these as questions):
{messages_formatted}

Requested question type (or leave empty to choose): {qtype_str}"""

    def _fallback_result() -> QuestionGenerationResult:
        fq, fd, ft = pick_fallback_question(
            previous_messages=previous_messages,
            question_index=question_index,
            question_type=question_type,
            suggested_difficulty=suggested_difficulty,
        )
        logger.info("Session Q&A: using static fallback question (LLM unavailable or failed).")
        return QuestionGenerationResult(question=fq, difficulty=fd, question_type=ft)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("Session Q&A: could not create OpenAI client: %s", e)
        return _fallback_result()

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
            return _fallback_result()

        content = _strip_json_fence(content)
        parsed = json.loads(content)
        question = (parsed.get("question") or "").strip()
        if not question:
            return _fallback_result()

        return QuestionGenerationResult(
            question=question,
            difficulty=parsed.get("difficulty"),
            question_type=parsed.get("question_type"),
        )
    except json.JSONDecodeError as e:
        logger.warning("Session Q&A question gen: invalid JSON from LLM: %s", e)
        return _fallback_result()
    except Exception as e:
        logger.warning("Session Q&A question gen: LLM call failed: %s", e)
        return _fallback_result()


# --- Greeting / off-topic / skip (ChatGPT-style, LLM-only) ---

# Sentinel returned when the user asks to skip to the next question (caller generates next question).
NEXT_QUESTION_SENTINEL = "__NEXT_QUESTION__"

# Fallback when we want a redirect but LLM fails or returns junk
DEFAULT_REDIRECT_MESSAGE = (
    "I'm here to help you practice. When you're ready, answer the question above and I'll give you feedback."
)

REDIRECT_SYSTEM_PROMPT = """You are a warm, supportive interview-practice coach (like a friendly mentor). The user is in a live practice session with one question on the table.

Your job — reply with exactly ONE of the following:

1. SUBSTANTIVE_ANSWER — if the user is clearly giving a real answer to the interview question (even if short, unsure, or imperfect).

2. NEXT_QUESTION — if the user clearly wants to skip to the next question (e.g. "next question", "move on", "skip", "I don't want to answer this", "let's move on", "next one please", "can we skip this one"). Use this when they are explicitly asking to advance, not when they are just saying they don't know (for that use a redirect).

3. Otherwise (greeting, off-topic, "I don't know", "hint?", "can you repeat?", small talk, or not attempting an answer) — reply with ONE short, natural sentence that:
   - Feels conversational and supportive (like ChatGPT)
   - Gently brings them back to the question, or encourages them to try
   - Does NOT sound robotic or formal

Good redirect examples (vary your style):
- "Hey! I'm here to help. When you're ready, just answer the question above and I'll give you feedback."
- "No worries — take your time. Share your answer when you're ready and I'll give you feedback."
- "That's okay! Give it your best shot when you can; I'll give you feedback and we can build from there."

Rules:
- Reply with ONLY one of: the exact text SUBSTANTIVE_ANSWER, the exact text NEXT_QUESTION, or one short redirect sentence. No preamble, no JSON, no quotation marks. Keep redirects to under 25 words."""


def _normalize_redirect_response(raw: str) -> Optional[str]:
    """Return a clean redirect message or None if it looks like SUBSTANTIVE_ANSWER, NEXT_QUESTION, or invalid."""
    s = (raw or "").strip()
    if not s:
        return None
    if "SUBSTANTIVE_ANSWER" in s.upper() or "NEXT_QUESTION" in s.upper():
        return None
    # Remove surrounding quotes if the model added them
    for q in ('"', "'", "«", "»", "`"):
        if s.startswith(q) and s.endswith(q) and len(s) > 1:
            s = s[1:-1].strip()
    # Cap length; if too long, use fallback
    max_len = 280
    if len(s) > max_len:
        s = s[: max_len - 3].rstrip() + "..."
    return s if s else None


async def classify_and_redirect(question: str, user_message: str) -> Optional[str]:
    """
    Classify user message. Returns:
    - None: substantive answer (caller should run full evaluation).
    - NEXT_QUESTION_SENTINEL: user asked to skip to next question (caller should generate next question).
    - str: redirect message for greeting/off-topic (caller should store as FEEDBACK with meta.redirect).
    Raises ValueError if agent disabled/API key missing or LLM fails.
    """
    if not _is_session_qa_available():
        raise ValueError(
            "Session Q&A agent is disabled (SESSION_QA_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )

    user_content = f"""Last question asked:
{question}

User message:
{user_message}"""

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
                {"role": "system", "content": REDIRECT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,  # some variety in redirects, still stable
        )
        content = (response.choices[0].message.content or "").strip()
        if "SUBSTANTIVE_ANSWER" in content.upper():
            return None
        if "NEXT_QUESTION" in content.upper():
            return NEXT_QUESTION_SENTINEL
        redirect = _normalize_redirect_response(content)
        if redirect is None:
            return None  # treat as substantive, run evaluation
        return redirect
    except Exception as e:
        logger.warning("Session Q&A classify_and_redirect: LLM call failed: %s", e)
        return None  # on failure, fall back to full evaluation


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


# Kept here (not in app.agents.fallback) — fallback package is questions-only.
_FALLBACK_EVAL_PLACEHOLDER_FEEDBACK = (
    "Personalized feedback is temporarily unavailable because the AI scoring service did not respond. "
    "Your answer was still saved. You can continue practicing; try again in a moment for a real score."
)


def _fallback_eval_result() -> AnswerEvaluationResult:
    """Placeholder when the evaluator LLM cannot be used (no heuristic scoring)."""
    logger.info("Session Q&A: using placeholder feedback (evaluator LLM unavailable).")
    return AnswerEvaluationResult(
        feedback=_FALLBACK_EVAL_PLACEHOLDER_FEEDBACK,
        score=50,
        dimension_tags=["offline", "general"],
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
    Raises ValueError if Session Q&A is disabled (no API key / agent off).
    If the LLM is unreachable or returns invalid output, returns offline placeholder feedback (score 50).
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
        return _fallback_eval_result()

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
            return _fallback_eval_result()

        content = _strip_json_fence(content)
        parsed = json.loads(content)
        feedback = (parsed.get("feedback") or "").strip()
        if not feedback:
            return _fallback_eval_result()

        raw_score = parsed.get("score")
        if raw_score is None:
            return _fallback_eval_result()
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
        return _fallback_eval_result()
    except Exception as e:
        logger.warning("Session Q&A answer eval: LLM call failed: %s", e)
        return _fallback_eval_result()


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


# --- Conversational Tutor Mode ---

TUTOR_CHAT_SYSTEM_PROMPT = """You are an expert career coach and interview tutor. Your goal is to have a natural, helpful conversation with the user.

Context you will receive:
- Role level: INTERN, ASE, SSE, or OTHER.
- Job posting entities (if any): job title, company, required skills, etc.
- Candidate resume entities (if any): skills, occupation, education, experience.

Rules:
- Act as a friendly, knowledgeable tutor helping the candidate prepare for interviews or improve their career skills.
- Read the conversation history to understand the user's current context and questions.
- If the user asks for hints, interview tips, or feedback on their resume, provide constructive, detailed advice.
- Do not generate interview questions unless the user explicitly asks for one.
- Keep your answers helpful, concise, and professional but conversational.
- Respond with a single string containing your reply. Do not use JSON."""


async def generate_tutor_chat_reply(
    role_level: str,
    job_entities: Dict[str, List[str]],
    resume_entities: Dict[str, List[str]],
    previous_messages: List[Dict[str, Any]],
    user_message: str,
) -> str:
    """
    Call LLM to generate a conversational tutor response based on the chat history.
    """
    if not _is_session_qa_available():
        raise ValueError(
            "Session Q&A agent is disabled (SESSION_QA_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )

    job_json = json.dumps(job_entities, ensure_ascii=False, indent=2)
    resume_json = json.dumps(resume_entities, ensure_ascii=False, indent=2)
    
    system_content = f"{TUTOR_CHAT_SYSTEM_PROMPT}\n\nContext:\nRole level: {role_level}\n\nJob posting:\n{job_json}\n\nResume:\n{resume_json}"

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_content}]
    
    # Add previous messages
    for msg in previous_messages[-30:]:  # Limit history to last 30 messages
        role = "user" if msg.get("sender") == "USER" else "assistant"
        content = msg.get("content", "")
        if content:
            messages.append({"role": role, "content": content})
            
    # Add current user message
    messages.append({"role": "user", "content": user_message})

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
            messages=messages,
            temperature=temperature,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")
            
        return content
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.warning("Session Q&A tutor chat: LLM call failed: %s", e)
        raise ValueError("Tutor chat generation failed.") from e

