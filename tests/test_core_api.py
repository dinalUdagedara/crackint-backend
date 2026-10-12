"""Auth, resumes, jobs, job postings, match and uploads (NER/LLM/S3 offline)."""

import uuid
from datetime import datetime, timedelta, timezone

from app.auth.jwt import create_access_token
from app.api.uploads import route as uploads_route
from tests.conftest import API, register_and_login

RESUME_TEXT = "Jane Doe\njane.doe@example.com\nSkills: Python, PostgreSQL, Docker\nSoftware Engineer at Acme"


# --- Auth -----------------------------------------------------------------------


async def test_register_login_me_and_profile_update(client):
    body = {"email": "jane@example.com", "password": "Password123!", "name": "Jane"}
    assert (await client.post(f"{API}/auth/register", json=body)).status_code in (200, 201)
    assert (await client.post(f"{API}/auth/register", json=body)).status_code == 400  # duplicate email

    r = await client.post(f"{API}/auth/login", json={"email": body["email"], "password": "wrong-password"})
    assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json={"email": body["email"], "password": body["password"]})
    headers = {"Authorization": f"Bearer {r.json()['payload']['access_token']}"}

    me = (await client.get(f"{API}/auth/me", headers=headers)).json()["payload"]
    assert (me["email"], me["name"], me["is_admin"]) == ("jane@example.com", "Jane", False)
    r = await client.patch(f"{API}/auth/me", json={"name": "Jane D."}, headers=headers)
    assert r.json()["payload"]["name"] == "Jane D."


async def test_invalid_expired_and_missing_tokens(client, auth_headers):
    assert (await client.get(f"{API}/auth/me")).status_code == 401
    assert (await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer nope"})).status_code == 401
    expired = create_access_token({"sub": str(uuid.uuid4())}, expires_delta=timedelta(minutes=-1))
    assert (await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {expired}"})).status_code == 401
    unknown_user = create_access_token({"sub": str(uuid.uuid4())})
    r = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {unknown_user}"})
    assert r.status_code == 401


# --- Resumes ----------------------------------------------------------------------


async def create_resume(client, headers, text=RESUME_TEXT):
    r = await client.post(f"{API}/resumes/extract", data={"text": text}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["payload"]


async def test_resume_crud_and_ownership(client, auth_headers):
    created = await create_resume(client, auth_headers)
    rid = created["resume_id"]
    assert "jane.doe@example.com" in created["entities"].get("EMAIL", [])

    listed = (await client.get(f"{API}/resumes", headers=auth_headers)).json()
    assert [r["id"] for r in listed["payload"]] == [rid]

    r = await client.patch(
        f"{API}/resumes/{rid}", json={"entities": {"SKILL": ["Python", "Kafka"]}}, headers=auth_headers
    )
    assert r.status_code == 200 and r.json()["payload"]["entities"]["SKILL"] == ["Python", "Kafka"]

    r = await client.put(f"{API}/resumes/{rid}", data={"text": "John Roe\njohn@example.com"}, headers=auth_headers)
    assert r.status_code == 200 and "john@example.com" in r.json()["payload"]["entities"].get("EMAIL", [])

    other = await register_and_login(client)
    for method, kwargs in [("get", {}), ("delete", {}), ("patch", {"json": {"entities": {"NAME": ["Mallory"]}}})]:
        r = await getattr(client, method)(f"{API}/resumes/{rid}", headers=other, **kwargs)
        assert r.status_code == 404, method
    assert (await client.get(f"{API}/resumes", headers=other)).json()["payload"] == []

    # "Delete all" only deletes the caller's resumes
    await create_resume(client, other)
    await client.delete(f"{API}/resumes", headers=other)
    assert (await client.get(f"{API}/resumes/{rid}", headers=auth_headers)).status_code == 200

    assert (await client.delete(f"{API}/resumes/{rid}", headers=auth_headers)).status_code == 200
    assert (await client.get(f"{API}/resumes/{rid}", headers=auth_headers)).status_code == 404


async def test_resume_extract_validation_and_scoring_disabled(client, auth_headers):
    assert (await client.post(f"{API}/resumes/extract", data={}, headers=auth_headers)).status_code == 400
    r = await client.post(
        f"{API}/resumes/extract",
        data={"text": "x"},
        files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 400  # file and text together
    rid = (await create_resume(client, auth_headers))["resume_id"]
    assert (await client.get(f"{API}/resumes/{rid}/score", headers=auth_headers)).status_code == 503


# --- Jobs & job postings -------------------------------------------------------------


async def test_job_extract_text(client, auth_headers):
    r = await client.post(f"{API}/jobs/extract", data={"text": "Senior Python developer at Acme"}, headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json()["payload"]["entities"], dict)
    assert (await client.post(f"{API}/jobs/extract", data={"text": "  "}, headers=auth_headers)).status_code == 400


async def create_job(client, headers, title="Backend Engineer", **extra):
    body = {"entities": {"JOB_TITLE": [title], "SKILLS_REQUIRED": ["Python", "Kafka"]}, "raw_text": title, **extra}
    r = await client.post(f"{API}/job-postings", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["payload"]["id"]


async def test_job_posting_crud_reorder_deadlines_and_ownership(client, auth_headers):
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).replace(tzinfo=None).isoformat()
    later = (datetime.now(timezone.utc) + timedelta(days=60)).replace(tzinfo=None).isoformat()
    a = await create_job(client, auth_headers, "A", deadline=soon)
    b = await create_job(client, auth_headers, "B", interview_at=later)

    r = await client.patch(f"{API}/job-postings/{a}", json={"notes": "Ask about on-call"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["payload"]["notes"] == "Ask about on-call"

    r = await client.put(f"{API}/job-postings/reorder", json={"order": [b, a]}, headers=auth_headers)
    assert r.status_code == 200
    listed = (await client.get(f"{API}/job-postings", headers=auth_headers)).json()["payload"]
    assert [j["id"] for j in listed][:2] == [b, a]

    near = (await client.get(f"{API}/job-postings/near-deadline", params={"days": 7}, headers=auth_headers)).json()
    assert [(i["job"]["id"], i["next_milestone_type"]) for i in near["payload"]] == [(a, "deadline")]

    other = await register_and_login(client)
    assert (await client.get(f"{API}/job-postings/{a}", headers=other)).status_code == 404
    assert (await client.delete(f"{API}/job-postings/{a}", headers=other)).status_code == 404
    assert (await client.delete(f"{API}/job-postings/{a}", headers=auth_headers)).status_code == 200
    assert (await client.get(f"{API}/job-postings/{a}", headers=auth_headers)).status_code == 404


# --- Match (skill gap) ----------------------------------------------------------------


async def test_skill_gap_analysis_is_stored_and_owner_only(client, auth_headers):
    rid = (await create_resume(client, auth_headers))["resume_id"]
    await client.patch(f"{API}/resumes/{rid}", json={"entities": {"SKILL": ["Python"]}}, headers=auth_headers)
    jid = await create_job(client, auth_headers)

    params = {"resume_id": rid, "job_posting_id": jid}
    assert (await client.get(f"{API}/match/skill-gap", params=params, headers=auth_headers)).status_code == 404
    r = await client.post(f"{API}/match/skill-gap", json=params, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert "Kafka" in r.json()["payload"]["missing_skills"]
    stored = await client.get(f"{API}/match/skill-gap", params=params, headers=auth_headers)
    assert stored.status_code == 200 and "Kafka" in stored.json()["payload"]["missing_skills"]

    other = await register_and_login(client)
    assert (await client.post(f"{API}/match/skill-gap", json=params, headers=other)).status_code == 404


# --- Uploads ----------------------------------------------------------------------------


async def test_image_upload(client, auth_headers, monkeypatch):
    png = ("cover.png", b"\x89PNG\r\n\x1a\nfake", "image/png")
    r = await client.post(f"{API}/uploads/image", files={"file": png}, headers=auth_headers)
    assert r.status_code == 503  # S3 not configured

    uploaded = {}

    def fake_upload(content, content_type, prefix):
        uploaded.update(content_type=content_type, prefix=prefix, size=len(content))
        return f"https://bucket.example.com/{prefix}/x.png"

    monkeypatch.setattr(uploads_route, "is_s3_uploads_configured", lambda: True)
    monkeypatch.setattr(uploads_route, "upload_image_to_s3", fake_upload)
    r = await client.post(f"{API}/uploads/image", params={"purpose": "profile"}, files={"file": png}, headers=auth_headers)
    assert r.json()["payload"]["url"] == "https://bucket.example.com/uploads/profile-images/x.png"
    assert uploaded == {"content_type": "image/png", "prefix": "uploads/profile-images", "size": 12}

    bad = ("notes.txt", b"hello", "text/plain")
    assert (await client.post(f"{API}/uploads/image", files={"file": bad}, headers=auth_headers)).status_code == 400
    assert (await client.post(f"{API}/uploads/image", files={"file": png})).status_code == 401
