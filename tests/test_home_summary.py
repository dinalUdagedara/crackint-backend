"""Home summary: cards from real data and onboarding steps."""

from tests.conftest import API


async def home(client, headers):
    r = await client.get(f"{API}/users/me/home-summary", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["payload"]


def card(payload, card_id):
    return next(c for c in payload["cards"] if c["id"] == card_id)


async def test_new_user_gets_onboarding_and_empty_cards(client, auth_headers):
    payload = await home(client, auth_headers)
    assert [c["id"] for c in payload["cards"]] == ["jump_back_in", "practice_next", "refine_cv", "readiness_tracker"]
    assert card(payload, "jump_back_in")["items"] == []
    assert card(payload, "practice_next")["items"] == []
    assert [(s["id"], s["done"]) for s in payload["onboarding"]] == [
        ("upload_cv", False), ("add_job", False), ("first_session", False), ("first_report", False)
    ]


async def test_active_sessions_first_and_completed_link_to_report(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    done_id = r.json()["payload"]["id"]
    await client.post(f"{API}/sessions/{done_id}/chat", json={"content": "start"}, headers=auth_headers)
    await client.post(f"{API}/sessions/{done_id}/chat", json={"content": "answer"}, headers=auth_headers)
    await client.post(f"{API}/sessions/{done_id}/complete", headers=auth_headers)
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    active_id = r.json()["payload"]["id"]

    # Touch the completed one last: it is still listed after the active one
    await client.patch(f"{API}/sessions/{done_id}", json={"title": "Done one"}, headers=auth_headers)
    items = card(await home(client, auth_headers), "jump_back_in")["items"]
    assert [i["session_id"] for i in items] == [active_id, done_id]
    assert items[0]["href"] == f"/sessions/{active_id}" and items[0]["description"] == "In progress"
    assert items[1]["href"] == f"/sessions/{done_id}/report" and items[1]["description"] == "Report ready"

    steps = {s["id"]: s["done"] for s in (await home(client, auth_headers))["onboarding"]}
    assert steps == {"upload_cv": False, "add_job": False, "first_session": True, "first_report": True}


async def test_practice_next_lists_weak_topics(client, auth_headers, fake_agents):
    r = await client.post(f"{API}/sessions", json={"mode": "QUICK_PRACTICE"}, headers=auth_headers)
    url = f"{API}/sessions/{r.json()['payload']['id']}/chat"
    await client.post(url, json={"content": "start"}, headers=auth_headers)
    fake_agents.eval_topic, fake_agents.eval_score = "SQL indexing", 40
    await client.post(url, json={"content": "weak"}, headers=auth_headers)
    fake_agents.eval_topic, fake_agents.eval_score = "teamwork", 95
    await client.post(url, json={"content": "strong"}, headers=auth_headers)

    items = card(await home(client, auth_headers), "practice_next")["items"]
    assert items[0] == {
        "title": "sql indexing",
        "description": "avg 40% · due now",
        "href": None,
        "session_id": None,
        "resume_id": None,
        "job_posting_id": None,
        "action_type": "start_focus_session",
        "topic": "sql indexing",
    }
    assert [i["topic"] for i in items] == ["sql indexing", "teamwork"]  # strong first answer = learning, not due
