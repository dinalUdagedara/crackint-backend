"""Tests for PATCH /auth/me (profile update)."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_engine
from app.main import get_app


@pytest.fixture(autouse=True)
async def dispose_async_engine_after_test():
    yield
    await async_engine.dispose()


def _client() -> AsyncClient:
    app = get_app()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_patch_me_updates_name():
    email = f"prof_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password12", "name": "Before"},
        )
        assert r.status_code == 201
        r2 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password12"},
        )
        assert r2.status_code == 200
        token = r2.json()["payload"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r3 = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"name": "After Name"},
        )
        assert r3.status_code == 200
        data = r3.json()
        assert data["success"] is True
        assert data["payload"]["name"] == "After Name"
        assert data["payload"]["email"] == email


@pytest.mark.asyncio
async def test_patch_me_updates_profile_image_url_only():
    email = f"pic_{uuid.uuid4().hex[:8]}@test.com"
    url = "https://bucket.s3.us-east-1.amazonaws.com/uploads/profile-images/abc.jpg"
    async with _client() as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password12", "name": "Pic User"},
        )
        r2 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password12"},
        )
        token = r2.json()["payload"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r3 = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"profile_image_url": url},
        )
        assert r3.status_code == 200
        assert r3.json()["payload"]["profile_image_url"] == url


@pytest.mark.asyncio
async def test_patch_me_400_when_empty_body():
    email = f"empty_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password12", "name": "U"},
        )
        r2 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password12"},
        )
        token = r2.json()["payload"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r3 = await client.patch("/api/v1/auth/me", headers=headers, json={})
        assert r3.status_code == 400
        assert "field" in r3.json().get("detail", "").lower()
