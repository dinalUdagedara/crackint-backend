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


async def test_get_my_home_summary_route_exists_and_shape():
    """GET /users/me/home-summary returns 200/401/403 and when 200 has three cards with expected shape."""
    async with _create_client() as client:
        resp = await client.get("/api/v1/users/me/home-summary")
        assert resp.status_code in (200, 401, 403)
    if resp.status_code != 200:
        return
    data = resp.json()
    assert data.get("success") is True
    payload = data.get("payload")
    assert payload is not None
    cards = payload.get("cards")
    assert isinstance(cards, list)
    assert len(cards) == 3
    ids = {c.get("id") for c in cards}
    assert ids == {"jump_back_in", "refine_cv", "readiness_tracker"}
    icons = {c.get("icon") for c in cards}
    assert icons == {"messages", "sparkles", "shield"}
    for card in cards:
        items = card.get("items", [])
        assert isinstance(items, list)
        for item in items:
            assert "title" in item and item["title"]
            has_action = (
                item.get("href")
                or item.get("session_id")
                or item.get("resume_id")
                or item.get("job_posting_id")
                or item.get("action_type")
            )
            assert has_action, f"Item should have href or an id or action_type: {item}"

