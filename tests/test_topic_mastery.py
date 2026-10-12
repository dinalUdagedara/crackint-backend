"""Spaced retry: topic mastery boxes, due topics, and weak topics returning in later sessions."""

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.agents.session_qa_agent import _parse_eval
from app.database import SessionLocal
from app.models import TopicMastery, User
from app.services.topic_mastery import (
    due_weak_topics,
    next_box,
    normalize_topic,
    record_attempt,
    utcnow,
)
from tests.conftest import API


def test_normalize_topic():
    assert normalize_topic("  SQL   Indexing. ") == "sql indexing"
    assert normalize_topic("") is None and normalize_topic(None) is None


@pytest.mark.parametrize("box,score,expected", [(2, 50, 0), (2, 75, 2), (2, 85, 3), (5, 95, 5), (0, 69.9, 0)])
def test_next_box(box, score, expected):
    assert next_box(box, score) == expected


def test_eval_parses_topic():
    r = _parse_eval('{"feedback": "ok", "score": 70, "dimension_tags": [], "topic": "Caching"}')
    assert r.topic == "Caching"
    assert _parse_eval('{"feedback": "ok", "score": 70}').topic is None


async def make_user():
    async with SessionLocal() as db:
        user = User(name="u", email="mastery@example.com", hashed_password="x")
        db.add(user)
        await db.commit()
        return user.id


async def test_record_attempt_and_due_topics(db_clean):
    user_id = await make_user()
    now = utcnow()
    async with SessionLocal() as db:
        weak = await record_attempt(db, user_id, "SQL Indexing", 40, now=now)
        assert (weak.topic, weak.box, weak.attempts, weak.next_due_at) == ("sql indexing", 0, 1, now)
        ok = await record_attempt(db, user_id, "Caching", 75, now=now)
        assert ok.box == 1 and ok.next_due_at == now + timedelta(days=1)
        strong = await record_attempt(db, user_id, "REST APIs", 90, now=now)
        assert strong.box == 2
        assert await record_attempt(db, user_id, None, 10) is None

        assert await due_weak_topics(db, user_id, now=now) == ["sql indexing"]
        # caching becomes due after a day; weakest box first
        later = now + timedelta(days=2)
        assert await due_weak_topics(db, user_id, now=later) == ["sql indexing", "caching"]
        assert await due_weak_topics(db, user_id, exclude=["SQL indexing"], now=later) == ["caching"]

        # repeated strong answers master the topic -> never due again
        t = now
        for _ in range(3):
            t += timedelta(days=40)
            row = await record_attempt(db, user_id, "sql indexing", 90, now=t)
        assert row.box == 3 and row.avg_score > 80
        assert "sql indexing" not in await due_weak_topics(db, user_id, now=t + timedelta(days=365))


async def answer_questions(client, headers, n, mode="QUICK_PRACTICE"):
    r = await client.post(f"{API}/sessions", json={"mode": mode}, headers=headers)
    sid = r.json()["payload"]["id"]
    url = f"{API}/sessions/{sid}/chat"
    await client.post(url, json={"content": "start"}, headers=headers)
    for i in range(n):
        await client.post(url, json={"content": f"answer {i}"}, headers=headers)
    return sid


async def test_weak_topic_returns_in_a_later_session_until_mastered(client, auth_headers, fake_agents):
    # Session A: a weak answer on "sql indexing"; it must not come back within session A.
    fake_agents.eval_topic, fake_agents.eval_score = "SQL indexing", 40
    sid_a = await answer_questions(client, auth_headers, 4)
    calls_a = fake_agents.calls["generate_next_question"]
    assert all(c["focus_topics"] is None for c in calls_a)
    msgs = (await client.get(f"{API}/sessions/{sid_a}/messages", headers=auth_headers)).json()["payload"]
    assert [m["meta"].get("topic") for m in msgs if m["type"] == "FEEDBACK"] == ["sql indexing"] * 4

    r = await client.get(f"{API}/users/me/topic-mastery", headers=auth_headers)
    [item] = r.json()["payload"]
    assert (item["topic"], item["status"], item["attempts"], item["due"]) == ("sql indexing", "weak", 4, True)

    # Session B: other topics; the 4th question (index 3) revisits the weak topic, once.
    fake_agents.calls.clear()
    fake_agents.eval_topic, fake_agents.eval_score = "teamwork", 75
    sid_b = await answer_questions(client, auth_headers, 7)
    focus = [c["focus_topics"] for c in fake_agents.calls["generate_next_question"]]
    assert focus[3] == ["sql indexing"]
    assert sum(1 for f in focus if f) == 1  # not repeated at question 8 in the same session
    msgs = (await client.get(f"{API}/sessions/{sid_b}/messages", headers=auth_headers)).json()["payload"]
    questions = [m for m in msgs if m["type"] == "QUESTION"]
    assert questions[3]["meta"]["retry_topic"] == "sql indexing"

    # Mastering it (strong scores over time) stops it coming back.
    async with SessionLocal() as db:
        await db.execute(
            update(TopicMastery).where(TopicMastery.topic == "sql indexing").values(box=3, avg_score=90)
        )
        await db.commit()
    fake_agents.calls.clear()
    await answer_questions(client, auth_headers, 4)
    assert all(c["focus_topics"] is None for c in fake_agents.calls["generate_next_question"])


async def test_focus_sessions_keep_their_own_focus(client, auth_headers, fake_agents):
    fake_agents.eval_topic, fake_agents.eval_score = "SQL indexing", 30
    await answer_questions(client, auth_headers, 1)
    fake_agents.calls.clear()
    fake_agents.eval_topic = "other"
    r = await client.post(
        f"{API}/sessions", json={"mode": "QUICK_PRACTICE", "focus_topics": ["Caching"]}, headers=auth_headers
    )
    url = f"{API}/sessions/{r.json()['payload']['id']}/chat"
    await client.post(url, json={"content": "start"}, headers=auth_headers)
    for i in range(4):
        await client.post(url, json={"content": f"a{i}"}, headers=auth_headers)
    assert {tuple(c["focus_topics"]) for c in fake_agents.calls["generate_next_question"]} == {("Caching",)}


async def test_offline_placeholder_evaluation_does_not_record_mastery(client, auth_headers, fake_agents):
    fake_agents.eval_topic = None  # the placeholder result has no topic
    await answer_questions(client, auth_headers, 2)
    r = await client.get(f"{API}/users/me/topic-mastery", headers=auth_headers)
    assert r.json()["payload"] == []
