"""Voice mock interviews: delivery metrics, VOICE_MOCK sessions, report delivery, text-to-speech."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import LLMUsage
from app.services import llm
from app.services.delivery import analyze_delivery, filler_counts, pace_hint
from tests.conftest import API


def test_filler_counts():
    text = "Um, so I, like, built it. You know, basically I'd like to say uh it worked. Umm."
    counts = filler_counts(text)
    assert counts == {"um": 2, "like": 1, "you know": 1, "basically": 1, "uh": 1}
    assert filler_counts("I would like to lead the team") == {}


def test_analyze_delivery():
    text = " ".join(["word"] * 150)
    meta = analyze_delivery(text, 60)
    assert meta["word_count"] == "150" and meta["wpm"] == "150" and meta["filler_count"] == "0"
    assert meta["fillers"] is None and meta["spoken"] == "true"
    assert analyze_delivery("too short", 2)["wpm"] is None
    assert [pace_hint(w) for w in (90, 140, 200, None)] == ["slow", "good", "fast", None]


async def test_voice_session_stores_delivery_and_report_summarizes_it(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "VOICE_MOCK"}, headers=auth_headers)
    assert r.json()["payload"]["mode"] == "VOICE_MOCK"
    sid = r.json()["payload"]["id"]
    url = f"{API}/sessions/{sid}/chat/stream"
    await client.post(url, json={"content": "ready"}, headers=auth_headers)
    answer = "Um, I led the migration, like, to Postgres and, you know, it went well. " * 3
    r = await client.post(url, json={"content": answer, "speaking_seconds": 20}, headers=auth_headers)
    assert r.status_code == 200
    await client.post(
        f"{API}/sessions/{sid}/chat", json={"content": "typed answer without timing"}, headers=auth_headers
    )

    msgs = (await client.get(f"{API}/sessions/{sid}/messages", headers=auth_headers)).json()["payload"]
    answers = [m for m in msgs if m["type"] == "ANSWER"]
    spoken = answers[1]["meta"]
    assert spoken["spoken"] == "true" and spoken["filler_count"] == "9" and spoken["wpm"] == "126"
    assert answers[2]["meta"] == {}

    report = (await client.post(f"{API}/sessions/{sid}/complete", headers=auth_headers)).json()["payload"]
    first, second = report["items"]
    assert first["delivery"]["fillers"] == {"um": 3, "like": 3, "you know": 3}
    assert first["delivery"]["pace"] == "good"
    assert second["delivery"] is None
    assert report["delivery"] == {
        "spoken_answers": 1,
        "average_wpm": 126,
        "pace": "good",
        "total_fillers": 9,
        "top_fillers": {"um": 3, "like": 3, "you know": 3},
    }


async def test_typed_sessions_have_no_delivery_section(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    await client.post(f"{API}/sessions/{sid}/chat", json={"content": "start"}, headers=auth_headers)
    await client.post(f"{API}/sessions/{sid}/chat", json={"content": "answer"}, headers=auth_headers)
    report = (await client.post(f"{API}/sessions/{sid}/complete", headers=auth_headers)).json()["payload"]
    assert report["delivery"] is None


@pytest.fixture
def fake_tts(monkeypatch):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=b"ID3fake-mp3")

    client = SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "get_client", lambda: client)
    return calls


async def test_tts_returns_audio_and_records_usage(client, auth_headers, fake_tts, monkeypatch):
    monkeypatch.setattr(settings, "TTS_MAX_CHARS", 10)
    r = await client.post(f"{API}/tts", json={"text": "  Tell me about yourself.  "}, headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3fake-mp3"
    assert fake_tts[0]["input"] == "Tell me ab" and fake_tts[0]["model"] == settings.TTS_MODEL
    async with SessionLocal() as db:
        [row] = (await db.execute(select(LLMUsage))).scalars().all()
    assert (row.agent, row.prompt_tokens, row.success) == ("tts", 10, True)
    assert row.cost_usd == pytest.approx(10 * 15 / 1_000_000)


async def test_tts_disabled_or_unavailable_is_503(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "TTS_ENABLED", False)
    assert (await client.post(f"{API}/tts", json={"text": "hi"}, headers=auth_headers)).status_code == 503
    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    assert (await client.post(f"{API}/tts", json={"text": "hi"}, headers=auth_headers)).status_code == 503


async def test_tts_requires_auth(client):
    assert (await client.post(f"{API}/tts", json={"text": "hi"})).status_code == 401
