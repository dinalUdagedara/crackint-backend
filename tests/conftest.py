"""
Shared test fixtures.

Tests run against a separate PostgreSQL database (default: crackint_test, override with
TEST_DATABASE_NAME). Create it once and migrate:

    createdb crackint_test
    DATABASE_NAME=crackint_test alembic upgrade head

Every table is truncated before each test that uses the database. LLM agents are replaced
with deterministic fakes via the `fake_agents` fixture; no network calls are made.
"""

import os

TEST_DATABASE_NAME = os.environ.get("TEST_DATABASE_NAME", "crackint_test")
if not TEST_DATABASE_NAME.endswith("_test"):
    raise RuntimeError("TEST_DATABASE_NAME must end with '_test' so tests never touch a real database.")
os.environ["DATABASE_NAME"] = TEST_DATABASE_NAME
# Never load NER models or call external services from tests.
os.environ["RESUME_NER_LOAD_DIR"] = ""
os.environ["JOB_POSTER_NER_LOAD_DIR"] = ""
os.environ["SESSION_QA_AGENT_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""

import importlib  # noqa: E402
import uuid  # noqa: E402
from typing import Any, Dict, List  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import app.models  # noqa: E402,F401  (registers tables on SQLModel.metadata)
from app.agents.session_qa_agent import (  # noqa: E402
    NEXT_QUESTION_SENTINEL,
    AnswerEvaluationResult,
    QuestionGenerationResult,
    SessionSummaryResult,
    SessionTitleResult,
)
from app.database import async_engine  # noqa: E402
from app.main import get_app  # noqa: E402

API = "/api/v1"


@pytest.fixture
async def db_clean():
    """Truncate all tables before the test; dispose pooled connections after (each test has its own loop)."""
    tables = ", ".join(f'"{t.name}"' for t in SQLModel.metadata.sorted_tables)
    async with async_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield
    await async_engine.dispose()


@pytest.fixture
async def client(db_clean):
    async with AsyncClient(transport=ASGITransport(app=get_app()), base_url="http://test") as c:
        yield c


async def register_and_login(client: AsyncClient, email: str | None = None) -> Dict[str, str]:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    password = "Password123!"
    r = await client.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Test User"})
    assert r.status_code in (200, 201), r.text
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["payload"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers(client) -> Dict[str, str]:
    return await register_and_login(client)


# --- Fake LLM agents --------------------------------------------------------

# Modules that import agent functions by name; each is patched if it has the attribute.
AGENT_CONSUMER_MODULES = [
    "app.agents.session_qa_agent",
    "app.api.session.route",
    "app.api.session.service",
]


class FakeAgents:
    """Deterministic stand-ins for the session Q&A agent. Records every call."""

    def __init__(self) -> None:
        self.calls: Dict[str, List[Dict[str, Any]]] = {}
        self.eval_score = 70
        self.fail: set[str] = set()

    def _record(self, name: str, **kwargs) -> None:
        self.calls.setdefault(name, []).append(kwargs)
        if name in self.fail:
            raise ValueError(f"{name} unavailable")

    async def generate_next_question(self, **kwargs):
        self._record("generate_next_question", **kwargs)
        n = kwargs.get("question_index", 0) + 1
        return QuestionGenerationResult(
            question=f"Question {n}?",
            difficulty=kwargs.get("suggested_difficulty"),
            question_type=kwargs.get("question_type") or "technical",
        )

    async def classify_and_redirect(self, question: str, user_message: str):
        self._record("classify_and_redirect", question=question, user_message=user_message)
        if user_message.strip().lower() == "hi":
            return "Hello! Let's get back to the question."
        if user_message.strip().lower() == "skip":
            return NEXT_QUESTION_SENTINEL
        return None

    async def evaluate_answer(self, **kwargs):
        self._record("evaluate_answer", **kwargs)
        return AnswerEvaluationResult(feedback="Solid answer.", score=self.eval_score, dimension_tags=["clarity", "depth"])

    async def generate_session_title(self, **kwargs):
        self._record("generate_session_title", **kwargs)
        return SessionTitleResult(title="Practice: Python basics")

    async def summarize_session_feedback(self, **kwargs):
        self._record("summarize_session_feedback", **kwargs)
        return SessionSummaryResult(strengths="Clear", areas_for_improvement="Depth")

    async def generate_tutor_chat_reply(self, **kwargs):
        self._record("generate_tutor_chat_reply", **kwargs)
        return "Tutor reply."

    # Streaming variants: same results, text split into small deltas.

    async def generate_next_question_stream(self, **kwargs):
        result = await self.generate_next_question(**kwargs)
        for part in _chunks(result.question):
            yield part
        yield result

    async def evaluate_answer_stream(self, **kwargs):
        result = await self.evaluate_answer(**kwargs)
        for part in _chunks(result.feedback):
            yield part
        yield result

    async def generate_tutor_chat_reply_stream(self, **kwargs):
        for part in _chunks(await self.generate_tutor_chat_reply(**kwargs)):
            yield part


def _chunks(text: str, size: int = 4) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


@pytest.fixture
def fake_agents(monkeypatch) -> FakeAgents:
    fakes = FakeAgents()
    names = [n for n in dir(FakeAgents) if not n.startswith("_") and callable(getattr(FakeAgents, n))]
    for mod_name in AGENT_CONSUMER_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        for name in names:
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, getattr(fakes, name))
    return fakes
