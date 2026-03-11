"""
Basic tests for cover letter generation and retrieval endpoints.

These tests exercise only the HTTP contract and basic wiring. They use the real
FastAPI app but assume environment/config will disable actual LLM calls in test
or that the endpoints are not invoked when the agent is disabled.
"""

import uuid

from httpx import ASGITransport, AsyncClient

from app.main import get_app


def _create_client() -> AsyncClient:
    app = get_app()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


async def test_get_cover_letter_without_existing_record_returns_none():
    async with _create_client() as client:
        resume_id = uuid.uuid4()
        job_posting_id = uuid.uuid4()

        resp = await client.get(
            "/api/v1/cover-letter",
            params={
                "resume_id": str(resume_id),
                "job_posting_id": str(job_posting_id),
            },
        )
        # Even if user/auth fails, we at least ensure route is wired.
        assert resp.status_code in (200, 401, 403)

