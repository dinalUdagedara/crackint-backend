"""Adaptive difficulty, role level inference, and question-type balance."""

import pytest

from app.services.difficulty import choose_difficulty, choose_question_type, infer_role_level
from tests.conftest import API


# --- Role level -------------------------------------------------------------


@pytest.mark.parametrize(
    "entities,expected",
    [
        ({"JOB_TITLE": ["Software Engineering Intern"]}, "INTERN"),
        ({"JOB_TITLE": ["Graduate Trainee - Finance"]}, "INTERN"),
        ({"JOB_TITLE": ["Senior Backend Engineer"]}, "SSE"),
        ({"JOB_TITLE": ["Tech Lead"]}, "SSE"),
        ({"JOB_TITLE": ["Staff Software Engineer"]}, "SSE"),
        ({"JOB_TITLE": ["Data Analyst"], "EXPERIENCE_REQUIRED": ["5+ years of experience"]}, "SSE"),
        ({"JOB_TITLE": ["Data Analyst"], "EXPERIENCE_REQUIRED": ["2-3 years"]}, "ASE"),
        ({"JOB_TITLE": ["Junior Developer"]}, "ASE"),
        ({"JOB_TITLE": ["Staff Accountant"]}, None),
        ({"JOB_TITLE": ["Marketing Manager"]}, None),
        ({}, None),
        (None, None),
    ],
)
def test_infer_role_level(entities, expected):
    assert infer_role_level(entities) == expected


# --- Difficulty -------------------------------------------------------------


def test_curve_before_any_scores():
    assert choose_difficulty(0, None, []).difficulty == "easy"
    assert choose_difficulty(3, "easy", []).difficulty == "medium"
    assert choose_difficulty(6, None, []).reason == "curve"


@pytest.mark.parametrize(
    "last,scores,expected,reason",
    [
        ("easy", [85], "medium", "step_up"),
        ("medium", [70, 90], "hard", "step_up"),  # avg 80
        ("hard", [95, 95], "hard", "step_up"),  # capped
        ("hard", [40], "medium", "step_down"),
        ("easy", [10, 20], "easy", "step_down"),  # floored
        ("medium", [60, 70], "medium", "hold"),
        ("medium", [20, 90, 85], "hard", "step_up"),  # only the last 2 count
    ],
)
def test_difficulty_adapts_to_scores(last, scores, expected, reason):
    choice = choose_difficulty(4, last, scores)
    assert (choice.difficulty, choice.reason) == (expected, reason)


def test_unknown_last_difficulty_uses_curve_as_base():
    assert choose_difficulty(0, None, [90]).difficulty == "medium"


# --- Question type balance --------------------------------------------------


@pytest.mark.parametrize(
    "types,expected",
    [
        ([], None),
        (["technical", "technical"], None),
        (["technical", "technical", "technical"], "behavioral"),
        (["behavioral", "technical", "technical"], None),
        (["technical", "behavioral", "behavioral"], "technical"),
        (["behavioral", "technical", "technical", "technical", "system_design"], "behavioral"),
    ],
)
def test_choose_question_type(types, expected):
    assert choose_question_type(types) == expected


# --- API ----------------------------------------------------------------------


async def create_job(client, headers, title):
    r = await client.post(
        f"{API}/job-postings",
        json={"entities": {"JOB_TITLE": [title]}, "raw_text": title},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["payload"]["id"]


async def test_session_role_level_inferred_overridden_and_used(client, auth_headers, fake_agents):
    job_id = await create_job(client, auth_headers, "Senior Platform Engineer")
    r = await client.post(f"{API}/sessions", json={"mode": "TARGETED", "job_posting_id": job_id}, headers=auth_headers)
    session = r.json()["payload"]
    assert session["role_level"] == "SSE"

    await client.post(f"{API}/sessions/{session['id']}/next-question", json={}, headers=auth_headers)
    assert fake_agents.calls["generate_next_question"][-1]["role_level"] == "SSE"

    r = await client.patch(f"{API}/sessions/{session['id']}", json={"role_level": "INTERN"}, headers=auth_headers)
    assert r.json()["payload"]["role_level"] == "INTERN"
    await client.post(f"{API}/sessions/{session['id']}/chat", json={"content": "an answer"}, headers=auth_headers)
    assert fake_agents.calls["evaluate_answer"][-1]["role_level"] == "INTERN"

    r = await client.post(
        f"{API}/sessions", json={"job_posting_id": job_id, "role_level": "ASE"}, headers=auth_headers
    )
    assert r.json()["payload"]["role_level"] == "ASE"


async def test_session_without_job_defaults_to_ase(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    session = r.json()["payload"]
    assert session["role_level"] is None
    await client.post(f"{API}/sessions/{session['id']}/next-question", json={}, headers=auth_headers)
    assert fake_agents.calls["generate_next_question"][-1]["role_level"] == "ASE"


async def test_chat_difficulty_steps_up_and_down_with_scores(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    url = f"{API}/sessions/{r.json()['payload']['id']}/chat"

    r = await client.post(url, json={"content": "start"}, headers=auth_headers)
    q1 = r.json()["payload"]["new_messages"][-1]
    assert q1["meta"]["difficulty"] == "easy" and q1["meta"]["difficulty_reason"] == "curve"

    fake_agents.eval_score = 92
    r = await client.post(url, json={"content": "great answer"}, headers=auth_headers)
    q2 = r.json()["payload"]["new_messages"][-1]
    assert q2["type"] == "QUESTION"
    assert (q2["meta"]["difficulty"], q2["meta"]["difficulty_reason"]) == ("medium", "step_up")

    fake_agents.eval_score = 20
    r = await client.post(url, json={"content": "weak answer"}, headers=auth_headers)
    q3 = r.json()["payload"]["new_messages"][-1]
    # avg of last two scores (92, 20) = 56 -> hold at medium
    assert (q3["meta"]["difficulty"], q3["meta"]["difficulty_reason"]) == ("medium", "hold")

    r = await client.post(url, json={"content": "another weak answer"}, headers=auth_headers)
    q4 = r.json()["payload"]["new_messages"][-1]
    assert (q4["meta"]["difficulty"], q4["meta"]["difficulty_reason"]) == ("easy", "step_down")


async def test_explicit_difficulty_still_wins(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    r = await client.post(
        f"{API}/sessions/{sid}/next-question", json={"prefer_difficulty": "hard"}, headers=auth_headers
    )
    assert r.json()["payload"]["difficulty"] == "hard"
    msgs = (await client.get(f"{API}/sessions/{sid}/messages", headers=auth_headers)).json()["payload"]
    assert msgs[0]["meta"]["difficulty_reason"] == "requested"


async def test_behavioral_question_requested_after_three_technical(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    url = f"{API}/sessions/{r.json()['payload']['id']}/next-question"
    for _ in range(3):
        await client.post(url, json={}, headers=auth_headers)
    assert [c["question_type"] for c in fake_agents.calls["generate_next_question"]] == [None, None, None]
    await client.post(url, json={}, headers=auth_headers)
    assert fake_agents.calls["generate_next_question"][-1]["question_type"] == "behavioral"
