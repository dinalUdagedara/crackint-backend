"""
Basic tests for prep session and message APIs.
"""

from httpx import AsyncClient

from app.main import get_app


async def _create_client() -> AsyncClient:
    app = get_app()
    return AsyncClient(app=app, base_url="http://test")


async def test_create_and_get_prep_session():
    client = await _create_client()
    async with client:
        # Create session without resume/job for now
        resp = await client.post(
            "/api/v1/sessions",
            json={"user_id": None, "resume_id": None, "job_posting_id": None, "mode": "TARGETED"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        session_id = data["payload"]["id"]

        # Fetch session
        resp_get = await client.get(f"/api/v1/sessions/{session_id}")
        assert resp_get.status_code == 200
        data_get = resp_get.json()
        assert data_get["success"] is True
        assert data_get["payload"]["id"] == session_id


async def test_append_and_list_messages():
    client = await _create_client()
    async with client:
        # Create session first
        resp = await client.post(
            "/api/v1/sessions",
            json={"user_id": None, "resume_id": None, "job_posting_id": None, "mode": "TARGETED"},
        )
        assert resp.status_code == 200
        session_id = resp.json()["payload"]["id"]

        # Append a message
        resp_msg = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "sender": "USER",
                "type": "QUESTION",
                "content": "Tell me about this role?",
                "metadata": {},
            },
        )
        assert resp_msg.status_code == 200
        msg_payload = resp_msg.json()["payload"]
        assert msg_payload["session_id"] == session_id

        # List messages
        resp_list = await client.get(f"/api/v1/sessions/{session_id}/messages")
        assert resp_list.status_code == 200
        list_payload = resp_list.json()["payload"]
        assert len(list_payload) >= 1
        assert list_payload[0]["content"] == "Tell me about this role?"

