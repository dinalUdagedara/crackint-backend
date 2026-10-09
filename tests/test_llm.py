"""Shared LLM client, usage/cost tracking, rate limiting, and the admin usage endpoint."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from app.agents import session_qa_agent
from app.api.rate_limit import SlidingWindowLimiter, llm_limiter
from app.config import settings
from app.database import SessionLocal
from app.models import LLMUsage, User
from app.services import llm
from tests.conftest import API


# --- Fake OpenAI client -------------------------------------------------------


def _completion(content: str, prompt_tokens: int = 100, completion_tokens: int = 20):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def _chunk(content=None, usage=None):
    choices = [SimpleNamespace(delta=SimpleNamespace(content=content))] if content is not None else []
    return SimpleNamespace(choices=choices, usage=usage)


class FakeCompletions:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return await self.responder(**kwargs)


class FakeClient:
    def __init__(self, responder):
        self.chat = SimpleNamespace(completions=FakeCompletions(responder))


@pytest.fixture
def fake_openai(monkeypatch):
    """Route every chat_completion through a fake client. Set .responder to control output."""
    holder = SimpleNamespace(client=None)

    def install(responder):
        holder.client = FakeClient(responder)
        monkeypatch.setattr(llm, "get_client", lambda: holder.client)
        return holder.client

    holder.install = install
    return holder


async def usage_rows():
    async with SessionLocal() as db:
        return list((await db.execute(select(LLMUsage).order_by(LLMUsage.created_at))).scalars().all())


# --- Client + cost ------------------------------------------------------------


def test_get_client_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    with pytest.raises(llm.LLMUnavailableError):
        llm.get_client()


def test_get_client_is_cached_and_configured(monkeypatch):
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-1")
    monkeypatch.setattr(settings, "LLM_TIMEOUT_SECONDS", 12.0)
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 3)
    c1 = llm.get_client()
    assert llm.get_client() is c1
    assert c1.max_retries == 3
    assert c1.timeout == 12.0
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-2")
    assert llm.get_client() is not c1


def test_estimate_cost():
    assert llm.estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)
    assert llm.estimate_cost_usd("gpt-4o-mini-2024-07-18", 1_000_000, 0) == pytest.approx(0.15)
    assert llm.estimate_cost_usd("gpt-4o-2024-08-06", 0, 1_000_000) == pytest.approx(10.0)
    assert llm.estimate_cost_usd("some-unknown-model", 10, 10) is None


# --- Usage tracking -----------------------------------------------------------


async def test_chat_completion_records_usage_with_attribution(db_clean, fake_openai):
    async def responder(**kwargs):
        return _completion("hi", prompt_tokens=1000, completion_tokens=500)

    client = fake_openai.install(responder)
    # Attribution comes from the request context; user/session ids need real rows (FKs).
    async with SessionLocal() as db:
        user = User(name="u", email="u@example.com", hashed_password="x")
        db.add(user)
        await db.commit()
    token = llm.current_user_id.set(user.id)
    try:
        resp = await llm.chat_completion(agent="test.agent", model="gpt-4o-mini", messages=[], temperature=0.1)
    finally:
        llm.current_user_id.reset(token)

    assert resp.choices[0].message.content == "hi"
    assert client.chat.completions.calls[0]["temperature"] == 0.1
    [row] = await usage_rows()
    assert (row.agent, row.model, row.success) == ("test.agent", "gpt-4o-mini", True)
    assert (row.prompt_tokens, row.completion_tokens) == (1000, 500)
    assert row.cost_usd == pytest.approx((1000 * 0.15 + 500 * 0.60) / 1_000_000)
    assert row.user_id == user.id and row.session_id is None


async def test_chat_completion_failure_is_recorded_and_reraised(db_clean, fake_openai):
    async def responder(**kwargs):
        raise TimeoutError("slow")

    fake_openai.install(responder)
    with pytest.raises(TimeoutError):
        await llm.chat_completion(agent="test.fail", model="gpt-4o-mini", messages=[])
    [row] = await usage_rows()
    assert row.success is False and row.cost_usd is None


async def test_usage_tracking_can_be_disabled(db_clean, fake_openai, monkeypatch):
    async def responder(**kwargs):
        return _completion("ok")

    fake_openai.install(responder)
    monkeypatch.setattr(settings, "LLM_USAGE_TRACKING_ENABLED", False)
    await llm.chat_completion(agent="x", model="gpt-4o-mini", messages=[])
    assert await usage_rows() == []


async def test_stream_yields_deltas_and_records_usage(db_clean, fake_openai):
    async def responder(**kwargs):
        assert kwargs["stream"] is True

        async def gen():
            for part in ["Hel", "lo", None]:
                yield _chunk(part) if part else _chunk(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))

        return gen()

    fake_openai.install(responder)
    parts = [p async for p in llm.chat_completion_stream(agent="test.stream", model="gpt-4o-mini", messages=[])]
    assert parts == ["Hel", "lo"]
    [row] = await usage_rows()
    assert (row.prompt_tokens, row.completion_tokens, row.success) == (10, 2, True)


# --- Agents go through the shared wrapper (end to end) -------------------------


async def test_chat_turn_with_real_agents_attributes_usage(client, auth_headers, fake_openai, monkeypatch):
    monkeypatch.setattr(settings, "SESSION_QA_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")

    async def responder(model, messages, **kwargs):
        system = messages[0]["content"]
        if system == session_qa_agent.REDIRECT_SYSTEM_PROMPT:
            return _completion("SUBSTANTIVE_ANSWER")
        return _completion(
            json.dumps(
                {
                    "question": "Explain Python generators?",
                    "difficulty": "easy",
                    "question_type": "technical",
                    "feedback": "Good.",
                    "score": 80,
                    "dimension_tags": ["clarity"],
                    "title": "Python practice",
                    "strengths": "s",
                    "areas_for_improvement": "a",
                }
            )
        )

    fake_openai.install(responder)
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    session_id = r.json()["payload"]["id"]
    user_id = r.json()["payload"]["user_id"]
    url = f"{API}/sessions/{session_id}/chat"
    r = await client.post(url, json={"content": "start"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    r = await client.post(url, json={"content": "Generators yield lazily."}, headers=auth_headers)
    assert r.status_code == 200, r.text
    types = [m["type"] for m in r.json()["payload"]["new_messages"]]
    assert types == ["ANSWER", "FEEDBACK", "QUESTION"]

    rows = await usage_rows()
    agents = [row.agent for row in rows]
    assert agents == [
        "session_qa.next_question",
        "session_qa.classify",
        "session_qa.evaluate",
        "session_qa.title",
        "session_qa.next_question",
    ]
    assert {str(row.user_id) for row in rows} == {user_id}
    assert {str(row.session_id) for row in rows} == {session_id}


# --- Rate limiting --------------------------------------------------------------


def test_sliding_window_limiter():
    lim = SlidingWindowLimiter()
    assert lim.hit("u", limit=2, window=60, now=0) is None
    assert lim.hit("u", limit=2, window=60, now=10) is None
    assert lim.hit("u", limit=2, window=60, now=20) == pytest.approx(40)
    assert lim.hit("other", limit=2, window=60, now=20) is None
    assert lim.hit("u", limit=2, window=60, now=60.5) is None


async def test_llm_endpoints_return_429_over_limit(client, auth_headers, fake_agents, monkeypatch):
    llm_limiter.reset()
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_PER_MINUTE", 2)
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    url = f"{API}/sessions/{r.json()['payload']['id']}/next-question"
    assert (await client.post(url, json={}, headers=auth_headers)).status_code == 200
    assert (await client.post(url, json={}, headers=auth_headers)).status_code == 200
    r = await client.post(url, json={}, headers=auth_headers)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    # Non-LLM endpoints are not limited
    assert (await client.get(f"{API}/sessions", headers=auth_headers)).status_code == 200
    llm_limiter.reset()


async def test_job_extract_requires_auth(client):
    r = await client.post(f"{API}/jobs/extract", data={"text": "Senior Python developer"})
    assert r.status_code == 401
    r = await client.post(f"{API}/resumes/preview-extract", data={"text": "John Doe"})
    assert r.status_code == 401


# --- Admin usage endpoint ---------------------------------------------------------


async def test_admin_llm_usage_summary(client, auth_headers, fake_openai):
    r = await client.get(f"{API}/admin/llm-usage", headers=auth_headers)
    assert r.status_code == 403

    me = (await client.get(f"{API}/auth/me", headers=auth_headers)).json()["payload"]
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.email == me["email"]).values(is_admin=True))
        await db.commit()

    async def responder(**kwargs):
        return _completion("x", prompt_tokens=1_000_000, completion_tokens=0)

    fake_openai.install(responder)
    await llm.chat_completion(agent="a.one", model="gpt-4o-mini", messages=[])
    await llm.chat_completion(agent="a.one", model="gpt-4o-mini", messages=[])
    await llm.chat_completion(agent="a.two", model="gpt-4o", messages=[])

    r = await client.get(f"{API}/admin/llm-usage", headers=auth_headers)
    assert r.status_code == 200, r.text
    p = r.json()["payload"]
    assert p["calls"] == 3
    assert p["cost_usd"] == pytest.approx(0.15 * 2 + 2.50)
    by_agent = {b["agent"]: b for b in p["breakdown"]}
    assert by_agent["a.one"]["calls"] == 2
    assert p["breakdown"][0]["agent"] == "a.two"  # most expensive first
