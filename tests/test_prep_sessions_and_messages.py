"""
Basic tests for prep session and message APIs.
"""

from httpx import ASGITransport, AsyncClient

from app.main import get_app


def _create_client() -> AsyncClient:
    app = get_app()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


async def test_create_and_get_prep_session():
    async with _create_client() as client:
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
    async with _create_client() as client:
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


async def test_delete_session_removes_messages():
    async with _create_client() as client:
        # Create session
        resp = await client.post(
            "/api/v1/sessions",
            json={
                "user_id": None,
                "resume_id": None,
                "job_posting_id": None,
                "mode": "QUICK_PRACTICE",
            },
        )
        assert resp.status_code == 200
        session_id = resp.json()["payload"]["id"]

        # Append a message
        resp_msg = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "sender": "USER",
                "type": "QUESTION",
                "content": "Hello",
                "metadata": {},
            },
        )
        assert resp_msg.status_code == 200

        # Delete the session
        resp_del = await client.delete(f"/api/v1/sessions/{session_id}")
        assert resp_del.status_code == 200
        data_del = resp_del.json()
        assert data_del["success"] is True
        assert data_del["payload"]["id"] == session_id

        # Session should be gone
        resp_get = await client.get(f"/api/v1/sessions/{session_id}")
        assert resp_get.status_code == 404

        # Messages endpoint should now 404 because session doesn't exist
        resp_msgs = await client.get(f"/api/v1/sessions/{session_id}/messages")
        assert resp_msgs.status_code == 404

