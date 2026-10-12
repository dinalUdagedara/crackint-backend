"""
Session API behaviour: CRUD, messages, and the Q&A flows (/next-question, /chat, /send,
/evaluate-answer). LLM agents are faked (see conftest.FakeAgents).
"""

import importlib
import uuid

import pytest

from tests.conftest import API, register_and_login


async def create_session(client, headers, **body):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE", **body}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["payload"]


async def get_messages(client, headers, session_id):
    r = await client.get(f"{API}/sessions/{session_id}/messages", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["payload"]


def shape(messages):
    return [(m["sender"], m["type"]) for m in messages]


# --- CRUD -------------------------------------------------------------------


async def test_session_crud_and_pagination(client, auth_headers):
    s1 = await create_session(client, auth_headers)
    await create_session(client, auth_headers, mode="TARGETED")
    assert s1["status"] == "ACTIVE"

    r = await client.get(f"{API}/sessions", headers=auth_headers)
    assert len(r.json()["payload"]) == 2
    assert r.json()["meta"] is None

    r = await client.get(f"{API}/sessions", params={"page": 1, "page_size": 1}, headers=auth_headers)
    body = r.json()
    assert len(body["payload"]) == 1
    assert body["meta"]["total_items"] == 2
    assert body["meta"]["total_pages"] == 2

    r = await client.patch(
        f"{API}/sessions/{s1['id']}", json={"title": "Renamed", "mode": "TUTOR_CHAT"}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["payload"]["summary"]["title"] == "Renamed"
    assert r.json()["payload"]["mode"] == "TUTOR_CHAT"

    r = await client.get(f"{API}/sessions/{s1['id']}", headers=auth_headers)
    assert r.json()["payload"]["readiness_score"] is None

    r = await client.delete(f"{API}/sessions/{s1['id']}", headers=auth_headers)
    assert r.json()["payload"] == {"id": s1["id"]}
    r = await client.get(f"{API}/sessions/{s1['id']}", headers=auth_headers)
    assert r.status_code == 404


async def test_other_users_session_is_404(client, auth_headers):
    s = await create_session(client, auth_headers)
    other = await register_and_login(client)
    for method, path in [
        ("get", ""),
        ("get", "/messages"),
        ("get", "/with-messages"),
        ("delete", ""),
    ]:
        r = await getattr(client, method)(f"{API}/sessions/{s['id']}{path}", headers=other)
        assert r.status_code == 404, (method, path)


async def test_append_and_list_messages_and_with_messages(client, auth_headers):
    s = await create_session(client, auth_headers)
    r = await client.post(
        f"{API}/sessions/{s['id']}/messages",
        json={"sender": "ASSISTANT", "type": "FEEDBACK", "content": "fb", "metadata": {"score": "80"}},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    msgs = await get_messages(client, auth_headers, s["id"])
    assert shape(msgs) == [("ASSISTANT", "FEEDBACK")]

    r = await client.get(f"{API}/sessions/{s['id']}/with-messages", headers=auth_headers)
    payload = r.json()["payload"]
    assert len(payload["messages"]) == 1
    assert payload["readiness_score"] == 80.0


# --- /next-question ---------------------------------------------------------


async def test_next_question_stores_question_with_curve_difficulty(client, auth_headers, fake_agents):
    s = await create_session(client, auth_headers)
    r = await client.post(f"{API}/sessions/{s['id']}/next-question", json={}, headers=auth_headers)
    assert r.status_code == 200, r.text
    p = r.json()["payload"]
    assert p["question"] == "Question 1?"
    assert p["difficulty"] == "easy"
    msgs = await get_messages(client, auth_headers, s["id"])
    assert shape(msgs) == [("ASSISTANT", "QUESTION")]
    assert msgs[0]["meta"]["difficulty"] == "easy"
    assert msgs[0]["id"] == p["message_id"]


async def test_next_question_503_when_agent_unavailable(client, auth_headers, fake_agents):
    fake_agents.fail.add("generate_next_question")
    s = await create_session(client, auth_headers)
    r = await client.post(f"{API}/sessions/{s['id']}/next-question", json={}, headers=auth_headers)
    assert r.status_code == 503


# --- /chat ------------------------------------------------------------------


async def test_chat_full_flow(client, auth_headers, fake_agents):
    s = await create_session(client, auth_headers)
    url = f"{API}/sessions/{s['id']}/chat"

    # First turn: no question yet -> generate first question
    r = await client.post(url, json={"content": "Let's start"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert shape(r.json()["payload"]["new_messages"]) == [("USER", "ANSWER"), ("ASSISTANT", "QUESTION")]

    # Greeting -> redirect feedback
    r = await client.post(url, json={"content": "hi"}, headers=auth_headers)
    new = r.json()["payload"]["new_messages"]
    assert shape(new) == [("USER", "ANSWER"), ("ASSISTANT", "FEEDBACK")]
    assert new[1]["meta"] == {"redirect": "true"}

    # Skip -> next question, no feedback
    r = await client.post(url, json={"content": "skip"}, headers=auth_headers)
    assert shape(r.json()["payload"]["new_messages"]) == [("USER", "ANSWER"), ("ASSISTANT", "QUESTION")]
    assert r.json()["payload"]["new_messages"][1]["content"] == "Question 2?"

    # Real answer -> feedback + next question
    r = await client.post(url, json={"content": "A real answer"}, headers=auth_headers)
    new = r.json()["payload"]["new_messages"]
    assert shape(new) == [("USER", "ANSWER"), ("ASSISTANT", "FEEDBACK"), ("ASSISTANT", "QUESTION")]
    assert new[1]["meta"]["score"] == "70"
    assert new[1]["meta"]["dimension_tags"] == "clarity,depth"
    assert fake_agents.calls["evaluate_answer"][0]["question"] == "Question 2?"

    # Session got a title and readiness from the scored feedback
    r = await client.get(f"{API}/sessions/{s['id']}", headers=auth_headers)
    sess = r.json()["payload"]
    assert sess["summary"]["title"] == "Practice: Python basics"
    assert sess["readiness_score"] == 70.0

    msgs = await get_messages(client, auth_headers, s["id"])
    assert len(msgs) == 9


async def test_chat_tutor_mode_replies_without_questions(client, auth_headers, fake_agents):
    s = await create_session(client, auth_headers, mode="TUTOR_CHAT")
    r = await client.post(f"{API}/sessions/{s['id']}/chat", json={"content": "How do I prep?"}, headers=auth_headers)
    new = r.json()["payload"]["new_messages"]
    assert shape(new) == [("USER", "ANSWER"), ("ASSISTANT", "FEEDBACK")]
    assert new[1]["content"] == "Tutor reply."
    assert "generate_next_question" not in fake_agents.calls


async def test_chat_returns_feedback_when_next_question_fails(client, auth_headers, fake_agents):
    s = await create_session(client, auth_headers)
    url = f"{API}/sessions/{s['id']}/chat"
    await client.post(url, json={"content": "start"}, headers=auth_headers)
    fake_agents.fail.add("generate_next_question")
    r = await client.post(url, json={"content": "An answer"}, headers=auth_headers)
    assert r.status_code == 200
    assert shape(r.json()["payload"]["new_messages"]) == [("USER", "ANSWER"), ("ASSISTANT", "FEEDBACK")]


async def test_chat_updates_summary_every_n_feedback(client, auth_headers, fake_agents, monkeypatch):
    for mod_name in ("app.api.session.route", "app.api.session.service"):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        if hasattr(mod, "SUMMARY_UPDATE_EVERY_N"):
            monkeypatch.setattr(mod, "SUMMARY_UPDATE_EVERY_N", 2)
    s = await create_session(client, auth_headers)
    url = f"{API}/sessions/{s['id']}/chat"
    await client.post(url, json={"content": "start"}, headers=auth_headers)
    await client.post(url, json={"content": "answer one"}, headers=auth_headers)
    assert "summarize_session_feedback" not in fake_agents.calls
    await client.post(url, json={"content": "answer two"}, headers=auth_headers)
    assert len(fake_agents.calls["summarize_session_feedback"]) == 1
    r = await client.get(f"{API}/sessions/{s['id']}", headers=auth_headers)
    assert r.json()["payload"]["summary"]["strengths"] == "Clear"


# --- /send ------------------------------------------------------------------


async def test_send_requires_a_question(client, auth_headers, fake_agents):
    s = await create_session(client, auth_headers)
    r = await client.post(f"{API}/sessions/{s['id']}/send", json={"content": "x"}, headers=auth_headers)
    assert r.status_code == 400


async def test_send_redirect_skip_and_evaluate(client, auth_headers, fake_agents):
    s = await create_session(client, auth_headers)
    await client.post(f"{API}/sessions/{s['id']}/next-question", json={}, headers=auth_headers)
    url = f"{API}/sessions/{s['id']}/send"

    r = await client.post(url, json={"content": "hi"}, headers=auth_headers)
    p = r.json()["payload"]
    assert p["redirect"] is True and p["score"] is None

    r = await client.post(url, json={"content": "skip"}, headers=auth_headers)
    p = r.json()["payload"]
    assert p["redirect"] is False and p["feedback"] == "Question 2?"

    r = await client.post(url, json={"content": "real"}, headers=auth_headers)
    p = r.json()["payload"]
    assert p["score"] == 70 and p["dimension_tags"] == ["clarity", "depth"] and p["redirect"] is False

    msgs = await get_messages(client, auth_headers, s["id"])
    assert shape(msgs) == [
        ("ASSISTANT", "QUESTION"),
        ("USER", "ANSWER"),
        ("ASSISTANT", "FEEDBACK"),
        ("USER", "ANSWER"),
        ("ASSISTANT", "QUESTION"),
        ("USER", "ANSWER"),
        ("ASSISTANT", "FEEDBACK"),
    ]


# --- /evaluate-answer -------------------------------------------------------


async def test_evaluate_answer_does_not_store_user_message(client, auth_headers, fake_agents):
    s = await create_session(client, auth_headers)
    r = await client.post(f"{API}/sessions/{s['id']}/evaluate-answer", json={"answer": "x"}, headers=auth_headers)
    assert r.status_code == 400

    await client.post(f"{API}/sessions/{s['id']}/next-question", json={}, headers=auth_headers)
    url = f"{API}/sessions/{s['id']}/evaluate-answer"
    r = await client.post(url, json={"answer": "hi"}, headers=auth_headers)
    assert r.json()["payload"]["redirect"] is True
    r = await client.post(url, json={"answer": "skip"}, headers=auth_headers)
    assert r.json()["payload"]["feedback"] == "Question 2?"
    r = await client.post(url, json={"answer": "real"}, headers=auth_headers)
    assert r.json()["payload"]["score"] == 70

    msgs = await get_messages(client, auth_headers, s["id"])
    assert shape(msgs) == [
        ("ASSISTANT", "QUESTION"),
        ("ASSISTANT", "FEEDBACK"),
        ("ASSISTANT", "QUESTION"),
        ("ASSISTANT", "FEEDBACK"),
    ]


@pytest.mark.parametrize("endpoint,body", [("send", {"content": "a"}), ("evaluate-answer", {"answer": "a"})])
async def test_classify_failure_is_503(client, auth_headers, fake_agents, endpoint, body):
    s = await create_session(client, auth_headers)
    await client.post(f"{API}/sessions/{s['id']}/next-question", json={}, headers=auth_headers)
    fake_agents.fail.add("classify_and_redirect")
    r = await client.post(f"{API}/sessions/{s['id']}/{endpoint}", json=body, headers=auth_headers)
    assert r.status_code == 503


async def test_unknown_session_is_404(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions/{uuid.uuid4()}/chat", json={"content": "x"}, headers=auth_headers)
    assert r.status_code == 404
