"""
Integration tests for Session Q&A endpoints (next-question, evaluate-answer).
Mocks the agent so no OpenAI API key is required. Requires DB for session/message persistence.
"""

import uuid
import pytest
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient

from app.main import get_app
from app.agents.session_qa_agent import (
    AnswerEvaluationResult,
    QuestionGenerationResult,
)


def _client() -> AsyncClient:
    app = get_app()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_next_question_404_when_session_not_found():
    """POST /sessions/{id}/next-question returns 404 for unknown session."""
    async with _client() as client:
        resp = await client.post(
            f"/api/v1/sessions/{uuid.uuid4()}/next-question",
            json={},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_next_question_503_when_agent_disabled():
    """POST /sessions/{id}/next-question returns 503 when Session Q&A agent is disabled."""
    async with _client() as client:
        resp_create = await client.post(
            "/api/v1/sessions",
            json={"user_id": None, "resume_id": None, "job_posting_id": None, "mode": "TARGETED"},
        )
        assert resp_create.status_code == 200
        session_id = resp_create.json()["payload"]["id"]

    with patch("app.api.session.route.generate_next_question", side_effect=ValueError("Session Q&A agent is disabled")):
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/sessions/{session_id}/next-question",
                json={},
            )
            assert resp.status_code == 503
            assert "disabled" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_next_question_200_and_stores_message():
    """POST /sessions/{id}/next-question returns 200 and stores QUESTION message when agent is mocked."""
    async with _client() as client:
        resp_create = await client.post(
            "/api/v1/sessions",
            json={"user_id": None, "resume_id": None, "job_posting_id": None, "mode": "TARGETED"},
        )
        assert resp_create.status_code == 200
        session_id = resp_create.json()["payload"]["id"]

    fake_result = QuestionGenerationResult(
        question="What is your greatest technical achievement?",
        difficulty="medium",
        question_type="technical",
    )

    with patch("app.api.session.route.generate_next_question", new_callable=AsyncMock, return_value=fake_result):
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/sessions/{session_id}/next-question",
                json={"question_type": "technical", "role_level": "ASE"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            payload = data["payload"]
            assert payload["question"] == "What is your greatest technical achievement?"
            assert payload["difficulty"] == "medium"
            assert payload["question_type"] == "technical"
            assert "message_id" in payload

            # Verify message was stored
            resp_messages = await client.get(f"/api/v1/sessions/{session_id}/messages")
            assert resp_messages.status_code == 200
            messages = resp_messages.json()["payload"]
            assert len(messages) == 1
            assert messages[0]["type"] == "QUESTION"
            assert messages[0]["sender"] == "ASSISTANT"
            assert messages[0]["content"] == "What is your greatest technical achievement?"


@pytest.mark.asyncio
async def test_evaluate_answer_404_when_session_not_found():
    """POST /sessions/{id}/evaluate-answer returns 404 for unknown session."""
    async with _client() as client:
        resp = await client.post(
            f"/api/v1/sessions/{uuid.uuid4()}/evaluate-answer",
            json={"answer": "My answer here."},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_evaluate_answer_400_when_no_question_in_session():
    """POST /sessions/{id}/evaluate-answer returns 400 when session has no QUESTION message."""
    async with _client() as client:
        resp_create = await client.post(
            "/api/v1/sessions",
            json={"user_id": None, "resume_id": None, "job_posting_id": None, "mode": "TARGETED"},
        )
        assert resp_create.status_code == 200
        session_id = resp_create.json()["payload"]["id"]

        resp = await client.post(
            f"/api/v1/sessions/{session_id}/evaluate-answer",
            json={"answer": "Some answer without a question first."},
        )
        assert resp.status_code == 400
        assert "no question" in resp.json().get("detail", "").lower() or "evaluate against" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_evaluate_answer_200_and_stores_feedback():
    """POST /sessions/{id}/evaluate-answer returns 200 and stores FEEDBACK message when agent is mocked."""
    async with _client() as client:
        resp_create = await client.post(
            "/api/v1/sessions",
            json={"user_id": None, "resume_id": None, "job_posting_id": None, "mode": "TARGETED"},
        )
        assert resp_create.status_code == 200
        session_id = resp_create.json()["payload"]["id"]

        # Add a QUESTION message so we have something to evaluate against
        await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "sender": "ASSISTANT",
                "type": "QUESTION",
                "content": "Tell me about a challenging project.",
                "metadata": {},
            },
        )

    fake_result = AnswerEvaluationResult(
        feedback="Good use of STAR. Add more metrics next time.",
        score=78,
        dimension_tags=["behavioral", "structure"],
    )

    with patch("app.api.session.route.evaluate_answer", new_callable=AsyncMock, return_value=fake_result):
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/sessions/{session_id}/evaluate-answer",
                json={"answer": "I led a migration project that reduced latency by 40%."},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            payload = data["payload"]
            assert payload["feedback"] == "Good use of STAR. Add more metrics next time."
            assert payload["score"] == 78
            assert payload["dimension_tags"] == ["behavioral", "structure"]
            assert "message_id" in payload

            # Verify feedback message was stored
            resp_messages = await client.get(f"/api/v1/sessions/{session_id}/messages")
            assert resp_messages.status_code == 200
            messages = resp_messages.json()["payload"]
            assert len(messages) == 2  # QUESTION + FEEDBACK
            feedback_msgs = [m for m in messages if m["type"] == "FEEDBACK"]
            assert len(feedback_msgs) == 1
            assert feedback_msgs[0]["content"] == "Good use of STAR. Add more metrics next time."
            meta = feedback_msgs[0].get("meta") or feedback_msgs[0].get("metadata") or {}
            assert meta.get("score") == "78"

            # Readiness is computed on request (GET); summary only every N feedbacks
            resp_session = await client.get(f"/api/v1/sessions/{session_id}")
            assert resp_session.status_code == 200
            session_payload = resp_session.json()["payload"]
            assert session_payload.get("readiness_score") == 78.0
            # Summary not updated after 1 eval (batch every 10)
