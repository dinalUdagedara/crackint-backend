"""
Deterministic stand-in replies for LLM_FAKE_RESPONSES=true (end-to-end tests, demos without an
OpenAI key). Replies are keyed by the calling agent and mimic each agent's expected output, so the
real agents, parsing and flows run unchanged. Never enabled in production (see config).
"""

import json
import re
from typing import Any, Dict, List

FAKE_MODEL = "fake"


def _user_text(messages: List[Dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""


def fake_reply(agent: str, messages: List[Dict[str, Any]]) -> str:
    user = _user_text(messages)
    if agent == "session_qa.next_question":
        n = user.count("(QUESTION)") + 1
        return json.dumps({
            "question": f"Practice question {n}: how would you design and test a REST API endpoint?",
            "difficulty": "easy",
            "question_type": "technical",
        })
    if agent == "session_qa.classify":
        answer = user.split("User message:", 1)[-1].strip().lower()
        if answer in {"hi", "hello", "hey"}:
            return "Hi! Take your time and answer the question above when you're ready."
        if "skip" in answer:
            return "NEXT_QUESTION"
        return "SUBSTANTIVE_ANSWER"
    if agent == "session_qa.evaluate":
        return json.dumps({
            "feedback": "Good structure. Add a concrete example with measurable results.",
            "score": 72,
            "dimension_tags": ["clarity", "depth"],
            "topic": "api design",
        })
    if agent == "session_qa.title":
        return json.dumps({"title": "API design practice"})
    if agent == "session_qa.summary":
        return json.dumps({"strengths": "Clear structure.", "areas_for_improvement": "Add measurable results."})
    if agent == "session_qa.tutor":
        return "Structure answers as situation, task, action and result, and end with a measurable outcome."
    if agent == "session_qa.report":
        indices = [int(i) for i in re.findall(r'"index": (\d+)', user)]
        return json.dumps({
            "items": [
                {"index": i, "topic": "api design", "model_answer": "A strong answer names the endpoint contract, validation, error codes and tests.", "star": None}
                for i in indices
            ],
            "strengths": ["You structure answers clearly."],
            "weak_topics": ["api design"],
            "summary": "You answered clearly; add concrete metrics to stand out.",
        })
    return "{}"


def chunks(text: str, size: int = 8) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
