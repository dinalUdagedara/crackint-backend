"""Deadline-aware prep plan."""

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Resume, User
from app.services.prep_plan import build_plan
from tests.conftest import API

TODAY = date(2026, 10, 12)


def kinds(tasks):
    return [t.kind for t in tasks]


def test_interview_plan_shape():
    tasks = build_plan(TODAY, TODAY + timedelta(days=5), "interview", ["Kubernetes", "Kafka"], ["sql indexing"], 72, set())
    assert kinds(tasks) == ["skill_gap", "weak_topic", "behavioral", "skill_gap", "mock_interview", "day_of"]
    assert [t.focus_topics for t in tasks[:2]] == [["Kubernetes"], ["sql indexing"]]
    assert tasks[0].is_today and tasks[0].minutes == 20  # avg >= 60 -> shorter drills
    assert tasks[-1].date == TODAY + timedelta(days=5)
    assert [t.day_index for t in tasks] == [1, 2, 3, 4, 5, 6]


def test_low_scores_mean_longer_drills_and_no_inputs_mean_practice():
    tasks = build_plan(TODAY, TODAY + timedelta(days=2), "interview", [], [], None, set())
    assert kinds(tasks) == ["practice", "mock_interview", "day_of"]
    assert tasks[0].minutes == 30


def test_deadline_plan_ends_with_application_task():
    tasks = build_plan(TODAY, TODAY + timedelta(days=1), "deadline", ["Go"], [], 50, set())
    assert kinds(tasks) == ["skill_gap", "deadline"]


def test_target_today_and_past():
    assert kinds(build_plan(TODAY, TODAY, "interview", [], [], None, set())) == ["day_of"]
    assert build_plan(TODAY, TODAY - timedelta(days=1), "interview", [], [], None, set()) == []


def test_plan_is_capped_and_done_marked_from_practice():
    tomorrow = TODAY + timedelta(days=1)
    tasks = build_plan(TODAY, TODAY + timedelta(days=30), "interview", ["a"], [], 50, {TODAY, tomorrow})
    assert len(tasks) == 14 + 1
    assert tasks[0].done is True and tasks[0].is_today
    assert tasks[1].done is False  # a future day is never done, even if a date matches
    assert all(not t.done for t in tasks[1:])


def test_duplicate_topics_are_not_repeated():
    tasks = build_plan(TODAY, TODAY + timedelta(days=3), "deadline", ["SQL Indexing"], ["sql indexing"], 50, set())
    assert [t.focus_topics for t in tasks if t.kind in ("skill_gap", "weak_topic")] == [["SQL Indexing"], ["SQL Indexing"]]


async def test_prep_plan_endpoint(client, auth_headers, fake_agents):
    me = (await client.get(f"{API}/auth/me", headers=auth_headers)).json()["payload"]
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == me["email"]))).scalar_one()
        db.add(Resume(user_id=user.id, entities={"SKILL": ["Python", "PostgreSQL"]}, raw_text="cv"))
        await db.commit()

    interview = (datetime.utcnow() + timedelta(days=4)).isoformat()
    r = await client.post(
        f"{API}/job-postings",
        json={
            "entities": {"JOB_TITLE": ["Backend Engineer"], "SKILLS_REQUIRED": ["Python", "Kafka", "Kubernetes"]},
            "raw_text": "jd",
            "interview_at": interview,
        },
        headers=auth_headers,
    )
    job_id = r.json()["payload"]["id"]

    plan = (await client.get(f"{API}/job-postings/{job_id}/prep-plan", headers=auth_headers)).json()["payload"]
    assert plan["target_type"] == "interview" and plan["days_left"] in (3, 4, 5)
    assert set(plan["missing_skills"]) >= {"Kafka", "Kubernetes"}
    assert plan["resume_id"] is not None
    assert plan["tasks"][0]["kind"] == "skill_gap" and plan["tasks"][0]["is_today"]
    assert plan["tasks"][-1]["kind"] == "day_of"
    assert plan["tasks"][0]["done"] is False

    # Practicing today for this job marks today's task done
    r = await client.post(f"{API}/sessions", json={"job_posting_id": job_id}, headers=auth_headers)
    sid = r.json()["payload"]["id"]
    await client.post(f"{API}/sessions/{sid}/chat", json={"content": "start"}, headers=auth_headers)
    await client.post(f"{API}/sessions/{sid}/chat", json={"content": "answer"}, headers=auth_headers)
    plan = (await client.get(f"{API}/job-postings/{job_id}/prep-plan", headers=auth_headers)).json()["payload"]
    assert plan["tasks"][0]["done"] is True
    assert plan["avg_score"] == 70.0


async def test_prep_plan_without_dates_and_ownership(client, auth_headers):
    r = await client.post(f"{API}/job-postings", json={"entities": {"JOB_TITLE": ["X"]}}, headers=auth_headers)
    job_id = r.json()["payload"]["id"]
    plan = (await client.get(f"{API}/job-postings/{job_id}/prep-plan", headers=auth_headers)).json()["payload"]
    assert plan["tasks"] == [] and plan["target_date"] is None

    from tests.conftest import register_and_login

    other = await register_and_login(client)
    r = await client.get(f"{API}/job-postings/{job_id}/prep-plan", headers=other)
    assert r.status_code == 404
