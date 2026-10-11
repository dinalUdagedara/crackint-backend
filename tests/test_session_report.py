"""End-of-session report: pairing, agent parsing, complete/report endpoints, focus topics."""

import uuid

import pytest

from app.agents.session_qa_agent import _question_user_content
from app.agents.session_report_agent import parse_report_insights
from app.api.session.service import collect_answered
from app.models import Message
from tests.conftest import API


def msg(type_, content="x", sender="ASSISTANT", **meta):
    return Message(id=uuid.uuid4(), session_id=uuid.uuid4(), sender=sender, type=type_, content=content, meta=meta)


def test_collect_answered_handles_skip_and_redirect():
    messages = [
        msg("QUESTION", "Q1"),
        msg("ANSWER", "hi", sender="USER"),
        msg("FEEDBACK", "Let's focus", redirect="true"),
        msg("ANSWER", "real answer 1", sender="USER"),
        msg("FEEDBACK", "fb1", score="70"),
        msg("QUESTION", "Q2"),
        msg("ANSWER", "skip", sender="USER"),
        msg("QUESTION", "Q3"),
        msg("ANSWER", "answer 3", sender="USER"),
        msg("FEEDBACK", "fb3", score="90"),
        msg("QUESTION", "Q4"),  # still open: not answered, not skipped
    ]
    answered, skipped = collect_answered(messages)
    assert [(a.question.content, a.answer.content, a.feedback.content) for a in answered] == [
        ("Q1", "real answer 1", "fb1"),
        ("Q3", "answer 3", "fb3"),
    ]
    assert skipped == 1


def test_parse_report_insights():
    parsed = parse_report_insights(
        '{"items": [{"index": 1, "topic": "Indexes", "model_answer": "Use B-trees.", '
        '"star": {"situation": true, "result": false}}, {"bad": 1}], '
        '"strengths": ["a", "b", "c", "d"], "weak_topics": ["x"], "summary": "Good."}'
    )
    assert len(parsed.items) == 1
    assert parsed.items[0].star.situation is True and parsed.items[0].star.result is False
    assert parsed.strengths == ["a", "b", "c"]
    with pytest.raises(ValueError):
        parse_report_insights("not json")


def test_question_prompt_includes_focus_topics():
    text = _question_user_content("ASE", {}, {}, [], None, 0, "easy", ["SQL indexing", "Caching"])
    assert "Focus topics" in text and "SQL indexing, Caching" in text
    assert "Focus topics" not in _question_user_content("ASE", {}, {}, [], None, 0, "easy")


async def run_session(client, headers, answers):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=headers)
    sid = r.json()["payload"]["id"]
    for content in ["start", *answers]:
        await client.post(f"{API}/sessions/{sid}/chat", json={"content": content}, headers=headers)
    return sid


async def test_complete_builds_and_stores_report(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    assert (await client.get(f"{API}/sessions/{sid}/report", headers=auth_headers)).status_code == 404

    url = f"{API}/sessions/{sid}/chat"
    await client.post(url, json={"content": "start"}, headers=auth_headers)
    fake_agents.eval_score = 80
    await client.post(url, json={"content": "answer one"}, headers=auth_headers)
    await client.post(url, json={"content": "skip"}, headers=auth_headers)
    fake_agents.eval_score = 50
    await client.post(url, json={"content": "answer three"}, headers=auth_headers)

    r = await client.post(f"{API}/sessions/{sid}/complete", headers=auth_headers)
    assert r.status_code == 200, r.text
    report = r.json()["payload"]
    assert report["generated_by"] == "llm"
    assert (report["questions_answered"], report["questions_skipped"]) == (2, 1)
    assert report["average_score"] == 65.0
    assert report["weak_topics"] == ["SQL indexing", "Trade-offs"]
    assert report["summary"] == "You did well."
    first = report["items"][0]
    assert (first["answer"], first["score"], first["topic"], first["model_answer"]) == (
        "answer one", 80, "Topic 1", "Model answer 1"
    )
    assert first["star"] is None  # fake questions are technical: STAR only for behavioral

    session = (await client.get(f"{API}/sessions/{sid}", headers=auth_headers)).json()["payload"]
    assert session["status"] == "COMPLETED"
    stored = (await client.get(f"{API}/sessions/{sid}/report", headers=auth_headers)).json()["payload"]
    assert stored == report

    # Completing again reuses the stored report; regenerate rebuilds it
    await client.post(f"{API}/sessions/{sid}/complete", headers=auth_headers)
    assert len(fake_agents.calls["generate_session_report"]) == 1
    await client.post(f"{API}/sessions/{sid}/complete", params={"regenerate": True}, headers=auth_headers)
    assert len(fake_agents.calls["generate_session_report"]) == 2


async def test_star_kept_for_behavioral_questions(client, auth_headers, fake_agents, monkeypatch):
    original = fake_agents.generate_next_question

    async def behavioral(**kwargs):
        result = await original(**kwargs)
        result.question_type = "behavioral"
        return result

    from app.api.session import service

    monkeypatch.setattr(service, "generate_next_question", behavioral)
    sid = await run_session(client, auth_headers, ["a STAR story"])
    report = (await client.post(f"{API}/sessions/{sid}/complete", headers=auth_headers)).json()["payload"]
    assert report["items"][0]["star"] == {
        "situation": True, "task": True, "action": True, "result": False, "note": "No result"
    }


async def test_basic_report_when_agent_unavailable(client, auth_headers, fake_agents):
    fake_agents.eval_score = 90
    sid = await run_session(client, auth_headers, ["great answer"])
    fake_agents.fail.add("generate_session_report")
    report = (await client.post(f"{API}/sessions/{sid}/complete", headers=auth_headers)).json()["payload"]
    assert report["generated_by"] == "basic"
    assert report["items"][0]["model_answer"] is None
    assert report["strengths"] == ["clarity", "depth"]  # tags with avg >= 75
    assert report["weak_topics"] == []


async def test_complete_empty_session(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    report = (await client.post(f"{API}/sessions/{sid}/complete", headers=auth_headers)).json()["payload"]
    assert (report["questions_answered"], report["generated_by"], report["items"]) == (0, "basic", [])
    assert "generate_session_report" not in fake_agents.calls


async def test_focus_topics_session_passes_topics_to_question_agent(client, auth_headers, fake_agents):
    r = await client.post(
        f"{API}/sessions",
        json={"mode": "QUICK_PRACTICE", "focus_topics": ["SQL indexing", " ", "Trade-offs"]},
        headers=auth_headers,
    )
    session = r.json()["payload"]
    assert session["focus_topics"] == ["SQL indexing", "Trade-offs"]
    await client.post(f"{API}/sessions/{session['id']}/next-question", json={}, headers=auth_headers)
    assert fake_agents.calls["generate_next_question"][-1]["focus_topics"] == ["SQL indexing", "Trade-offs"]
