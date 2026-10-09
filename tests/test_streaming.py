"""Streaming chat: JSON field extraction, streaming agents, and the SSE endpoint."""

import json
from types import SimpleNamespace

import pytest

from app.agents import session_qa_agent
from app.agents.json_stream import JsonStringFieldExtractor
from app.config import settings
from app.services import llm
from tests.conftest import API, register_and_login


# --- JsonStringFieldExtractor ---------------------------------------------------

DOC = json.dumps(
    {"score": 80, "feedback": 'Good "STAR" use.\nTry café \\ more 🚀 depth', "dimension_tags": ["x"]},
    ensure_ascii=True,
)
EXPECTED = 'Good "STAR" use.\nTry café \\ more 🚀 depth'


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 1000])
def test_extractor_any_chunking(size):
    ex = JsonStringFieldExtractor("feedback")
    out = "".join(ex.feed(DOC[i : i + size]) for i in range(0, len(DOC), size))
    assert out == EXPECTED
    assert ex.done


def test_extractor_unicode_unescaped_and_missing_field():
    ex = JsonStringFieldExtractor("question")
    assert ex.feed('{"question": "Pourquoi é') == "Pourquoi é"
    assert ex.feed('?", "difficulty": "easy"}') == "?"
    ex2 = JsonStringFieldExtractor("question")
    assert ex2.feed('{"other": "x"}') == ""
    assert not ex2.done


def test_extractor_ignores_text_after_value():
    ex = JsonStringFieldExtractor("feedback")
    assert ex.feed('{"feedback": "a"} {"feedback": "b"}') == "a"
    assert ex.feed('more') == ""


# --- Streaming agents against a fake OpenAI stream --------------------------------


def _chunk(content=None, usage=None):
    choices = [SimpleNamespace(delta=SimpleNamespace(content=content))] if content is not None else []
    return SimpleNamespace(choices=choices, usage=usage)


@pytest.fixture
def openai_stream(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_QA_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_USAGE_TRACKING_ENABLED", False)
    state = SimpleNamespace(text="", fail_after=None)

    async def create(**kwargs):
        async def gen():
            for i in range(0, len(state.text), 3):
                if state.fail_after is not None and i >= state.fail_after:
                    raise ConnectionError("dropped")
                yield _chunk(state.text[i : i + 3])
            yield _chunk(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

        return gen()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "get_client", lambda: client)
    monkeypatch.setattr(session_qa_agent, "get_client", lambda: client)
    return state


async def _collect(agen):
    deltas, final = [], None
    async for item in agen:
        if isinstance(item, str):
            deltas.append(item)
        else:
            final = item
    return "".join(deltas), final


async def test_evaluate_answer_stream_yields_feedback_then_result(openai_stream):
    openai_stream.text = json.dumps({"feedback": "Clear and structured.", "score": 88, "dimension_tags": ["clarity"]})
    text, result = await _collect(
        session_qa_agent.evaluate_answer_stream(
            question="Q", answer="A", role_level="ASE", job_entities={}, resume_entities={}
        )
    )
    assert text == "Clear and structured."
    assert (result.feedback, result.score, result.dimension_tags) == ("Clear and structured.", 88, ["clarity"])


async def test_evaluate_answer_stream_falls_back_when_stream_drops(openai_stream):
    openai_stream.text = json.dumps({"feedback": "Partial text that gets cut", "score": 70})
    openai_stream.fail_after = 15
    _, result = await _collect(
        session_qa_agent.evaluate_answer_stream(
            question="Q", answer="A", role_level="ASE", job_entities={}, resume_entities={}
        )
    )
    assert result.score == 50  # offline placeholder, same as non-streaming evaluate_answer


async def test_question_stream_and_invalid_json_fallback(openai_stream):
    openai_stream.text = '```json\n{"question": "Explain indexes?", "difficulty": "medium"}\n```'
    text, result = await _collect(
        session_qa_agent.generate_next_question_stream(
            role_level="ASE", job_entities={}, resume_entities={}, previous_messages=[]
        )
    )
    assert text == "Explain indexes?" and result.question == "Explain indexes?" and result.difficulty == "medium"

    openai_stream.text = "not json at all"
    _, result = await _collect(
        session_qa_agent.generate_next_question_stream(
            role_level="ASE", job_entities={}, resume_entities={}, previous_messages=[]
        )
    )
    assert result.question  # static fallback bank


async def test_tutor_stream_yields_plain_text(openai_stream):
    openai_stream.text = "Practice STAR stories."
    parts = [
        p
        async for p in session_qa_agent.generate_tutor_chat_reply_stream(
            role_level="ASE", job_entities={}, resume_entities={}, previous_messages=[], user_message="hi"
        )
    ]
    assert "".join(parts) == "Practice STAR stories."


# --- SSE endpoint -------------------------------------------------------------------


def parse_sse(body: str):
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def stream_turn(client, headers, session_id, content):
    r = await client.post(f"{API}/sessions/{session_id}/chat/stream", json={"content": content}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return parse_sse(r.text)


def stored_shape(messages):
    return [(m["sender"], m["type"], m["content"], {k: v for k, v in m["meta"].items()}) for m in messages]


async def test_stream_stores_same_messages_as_chat(client, auth_headers, fake_agents):
    conversation = ["start", "hi", "skip", "A real answer", "Another answer"]
    shapes = []
    for endpoint in ("chat", "chat/stream"):
        r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
        sid = r.json()["payload"]["id"]
        for content in conversation:
            r = await client.post(f"{API}/sessions/{sid}/{endpoint}", json={"content": content}, headers=auth_headers)
            assert r.status_code == 200
        msgs = (await client.get(f"{API}/sessions/{sid}/messages", headers=auth_headers)).json()["payload"]
        shapes.append(stored_shape(msgs))
        title = (await client.get(f"{API}/sessions/{sid}", headers=auth_headers)).json()["payload"]["summary"]["title"]
        assert title == "Practice: Python basics"
    assert shapes[0] == shapes[1]


async def test_stream_events_for_an_answer(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    events = await stream_turn(client, auth_headers, sid, "start")
    assert [e for e, _ in events][0] == "message"
    assert events[-1] == ("done", {"status": "Chat turn processed: first question generated."})

    events = await stream_turn(client, auth_headers, sid, "My answer")
    names = [e for e, _ in events]
    messages = [d["message"] for e, d in events if e == "message"]
    assert [m["type"] for m in messages] == ["ANSWER", "FEEDBACK", "QUESTION"]
    feedback_text = "".join(d["text"] for e, d in events if e == "feedback.delta")
    question_text = "".join(d["text"] for e, d in events if e == "question.delta")
    assert feedback_text == messages[1]["content"] == "Solid answer."
    assert question_text == messages[2]["content"]
    # deltas arrive before their stored message; feedback before question
    assert names.index("feedback.delta") < names.index("question.delta")
    assert names[-1] == "done"


async def test_stream_redirect_discards_speculative_evaluation(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    await stream_turn(client, auth_headers, sid, "start")
    events = await stream_turn(client, auth_headers, sid, "hi")
    assert "feedback.delta" not in [e for e, _ in events]
    messages = [d["message"] for e, d in events if e == "message"]
    assert [m["meta"].get("redirect") for m in messages] == [None, "true"]
    assert "score" not in messages[1]["meta"]


async def test_stream_tutor_mode(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "TUTOR_CHAT"}, headers=auth_headers)
    events = await stream_turn(client, auth_headers, r.json()["payload"]["id"], "How to prep?")
    assert "".join(d["text"] for e, d in events if e == "feedback.delta") == "Tutor reply."
    assert events[-2][1]["message"]["content"] == "Tutor reply."


async def test_stream_agent_unavailable_emits_error_event(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    await stream_turn(client, auth_headers, sid, "start")
    fake_agents.fail.add("classify_and_redirect")
    events = await stream_turn(client, auth_headers, sid, "answer")
    assert events[0][0] == "message"  # user message is stored first, as in /chat
    assert events[-1] == ("error", {"status": 503, "detail": "classify_and_redirect unavailable"})


async def test_stream_feedback_kept_when_next_question_fails(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    await stream_turn(client, auth_headers, sid, "start")
    fake_agents.fail.add("generate_next_question")
    events = await stream_turn(client, auth_headers, sid, "answer")
    assert [d["message"]["type"] for e, d in events if e == "message"] == ["ANSWER", "FEEDBACK"]
    assert events[-1][1]["status"].endswith("(next question generation failed).")


async def test_stream_requires_ownership(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    other = await register_and_login(client)
    r = await client.post(
        f"{API}/sessions/{r.json()['payload']['id']}/chat/stream", json={"content": "x"}, headers=other
    )
    assert r.status_code == 404
