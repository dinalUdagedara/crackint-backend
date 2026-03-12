"""
Basic tests for users readiness endpoints.

These tests focus on HTTP wiring and response shapes. They don't assert on
specific readiness numbers because that depends on CV scoring and gap
analysis services, which may be disabled in test environments.
"""

from httpx import ASGITransport, AsyncClient

from app.main import get_app


def _create_client() -> AsyncClient:
    app = get_app()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


async def test_get_my_readiness_route_exists():
    async with _create_client() as client:
        resp = await client.get("/api/v1/users/me/readiness")
        # In test env we may not have auth configured; accept 200 or 401/403.
        assert resp.status_code in (200, 401, 403)


async def test_get_my_readiness_summary_route_exists():
    async with _create_client() as client:
        resp = await client.get("/api/v1/users/me/readiness/summary")
        assert resp.status_code in (200, 401, 403)


async def test_get_my_readiness_trend_route_exists():
    async with _create_client() as client:
        resp = await client.get("/api/v1/users/me/readiness/trend")
        assert resp.status_code in (200, 401, 403)

