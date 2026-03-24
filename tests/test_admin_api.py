"""
Tests for admin API: authz, user CRUD, session list, user delete cascade.
Requires PostgreSQL and applied migrations (including users.is_admin).

DB helpers use sync psycopg2 to avoid mixing async SQLAlchemy sessions with the
httpx ASGI transport event loop.
"""

import uuid

import psycopg2
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import async_engine
from app.main import get_app


@pytest.fixture(autouse=True)
async def dispose_async_engine_after_test():
    """Avoid asyncpg pool connections bound to a stale asyncio loop between tests."""
    yield
    await async_engine.dispose()


def _pg_conn():
    return psycopg2.connect(
        host=settings.DATABASE_HOST,
        port=settings.DATABASE_PORT,
        dbname=settings.DATABASE_NAME,
        user=settings.DATABASE_USER,
        password=settings.DATABASE_PASSWORD,
    )


def _set_admin_sync(email: str, is_admin: bool = True) -> None:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_admin = %s WHERE email = %s",
            (is_admin, email),
        )
        conn.commit()
    finally:
        conn.close()


def _get_user_id_str(email: str) -> str:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"no user for email {email}")
        return str(row[0])
    finally:
        conn.close()


def _seed_victim_prep_session_and_resume(victim_id: str) -> None:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prep_sessions (
                id, user_id, resume_id, job_posting_id, mode, status, summary, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), %s::uuid, NULL, NULL, 'TARGETED', 'ACTIVE', '{}'::jsonb,
                current_timestamp(0), current_timestamp(0)
            )
            """,
            (victim_id,),
        )
        cur.execute(
            """
            INSERT INTO resumes (id, user_id, entities, created_at, updated_at)
            VALUES (gen_random_uuid(), %s::uuid, '{}'::jsonb, current_timestamp(0), current_timestamp(0))
            """,
            (victim_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _count_users(user_id: str) -> int:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM users WHERE id = %s::uuid", (user_id,))
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def _count_prep_for_user(user_id: str) -> int:
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM prep_sessions WHERE user_id = %s::uuid",
            (user_id,),
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def _client() -> AsyncClient:
    app = get_app()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


async def _register(client: AsyncClient, email: str, password: str = "password12") -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Test User"},
    )
    assert resp.status_code == 201, resp.text


async def _login(client: AsyncClient, email: str, password: str = "password12") -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["payload"]["access_token"]


@pytest.mark.asyncio
async def test_admin_routes_403_for_non_admin():
    email = f"user_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        await _register(client, email)
        token = await _login(client, email)
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403
        assert "Admin access required" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_admin_list_users_and_sessions():
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        await _register(client, admin_email)
        _set_admin_sync(admin_email, True)
        token = await _login(client, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/admin/users?page=1&page_size=10", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["payload"], list)
        assert data["meta"]["total_items"] >= 1

        resp_s = await client.get("/api/v1/admin/sessions?page=1&page_size=10", headers=headers)
        assert resp_s.status_code == 200
        assert resp_s.json()["success"] is True


@pytest.mark.asyncio
async def test_admin_patch_user_duplicate_email_400():
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    other_email = f"other_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        await _register(client, admin_email)
        await _register(client, other_email)
        _set_admin_sync(admin_email, True)
        token = await _login(client, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        other_id = _get_user_id_str(other_email)

        resp = await client.patch(
            f"/api/v1/admin/users/{other_id}",
            headers=headers,
            json={"email": admin_email},
        )
        assert resp.status_code == 400
        assert "Email already registered" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_admin_patch_user_updates_name():
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        await _register(client, admin_email)
        _set_admin_sync(admin_email, True)
        token = await _login(client, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        uid = _get_user_id_str(admin_email)

        new_name = f"Renamed {uuid.uuid4().hex[:6]}"
        resp = await client.patch(
            f"/api/v1/admin/users/{uid}",
            headers=headers,
            json={"name": new_name},
        )
        assert resp.status_code == 200
        assert resp.json()["payload"]["name"] == new_name


@pytest.mark.asyncio
async def test_admin_delete_user_removes_related_data():
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    victim_email = f"victim_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        await _register(client, admin_email)
        await _register(client, victim_email)
        _set_admin_sync(admin_email, True)

        victim_id = _get_user_id_str(victim_email)
        _seed_victim_prep_session_and_resume(victim_id)

        token = await _login(client, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.delete(f"/api/v1/admin/users/{victim_id}", headers=headers)
        assert resp.status_code == 200
        payload = resp.json()["payload"]
        assert payload["prep_sessions_deleted"] >= 1
        assert payload["resumes_deleted"] >= 1

        assert _count_users(victim_id) == 0
        assert _count_prep_for_user(victim_id) == 0


@pytest.mark.asyncio
async def test_admin_cannot_delete_self():
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    async with _client() as client:
        await _register(client, admin_email)
        _set_admin_sync(admin_email, True)
        token = await _login(client, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        uid = _get_user_id_str(admin_email)

        resp = await client.delete(f"/api/v1/admin/users/{uid}", headers=headers)
        assert resp.status_code == 403
        assert "own account" in resp.json().get("detail", "").lower()
