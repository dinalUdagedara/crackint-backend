# Next Steps Plan — Crackint Backend

After authentication (register, login, JWT, `/auth/me`) is in place, here’s a focused plan for what to do next.

---

## 1. Wire auth to resources (high priority)

Right now **resumes**, **job postings**, and **prep sessions** still accept optional `user_id` and don’t require a logged-in user. The next step is to make these resources **user-scoped** and **protected**.

### 1.1 Resumes

- **List** `GET /resumes`: Require auth; default to current user’s resumes only. Optionally keep `user_id` query for admins later, or remove it.
- **Get by ID** `GET /resumes/{resume_id}`: Require auth; return 403 if the resume’s `user_id` is not the current user (or 404 to avoid leaking existence).
- **Upload / create** `POST /resumes` (extract + save): Require auth; set `user_id = current_user.id` (remove optional `user_id` query/body).
- **Update / delete**: Same rule — require auth and ensure the resource belongs to `current_user.id`.

### 1.2 Job postings

- **List** `GET /job-postings`: Require auth; list only current user’s job postings (or add optional `user_id` filter for admins).
- **Get by ID** `GET /job-postings/{id}`: Require auth; 403/404 if not owner.
- **Create** `POST /job-postings`: Require auth; set `user_id = current_user.id` from token (ignore or remove `user_id` from request body).

### 1.3 Prep sessions

- **Create** `POST /sessions`: Require auth; set `user_id = current_user.id` (from token), not from body.
- **List** `GET /sessions`: Require auth; filter by `current_user.id` so users only see their own sessions.
- **Get by ID** and all session operations (chat, evaluate, etc.): Require auth and ensure the session’s `user_id` matches `current_user.id` (403/404 if not).

### 1.4 Implementation pattern

- Add `current_user: User = Depends(get_current_user)` to every endpoint that should be protected.
- Set `user_id = current_user.id` when creating resumes, job postings, and sessions.
- For list endpoints: filter by `Resume.user_id == current_user.id` (and same for JobPosting, PrepSession).
- For get/update/delete: load the resource, then check `resource.user_id == current_user.id`; if not, raise 403 or 404.

---

## 2. Security and config

- **JWT secret**: Ensure `JWT_SECRET` is set in production (e.g. in `.env`) to a long, random value (32+ chars). Remove or override the default `"change-me-in-production-min-32-chars"`.
- **Optional**: Add a simple env check at startup that warns or fails if `JWT_SECRET` is still the default when not in dev.

---

## 3. API consistency

- **Optional**: Add an optional dependency `get_current_user_optional` that returns `User | None` for endpoints that can work with or without auth (e.g. public job listings later). Not required for the first pass.
- After wiring auth, remove or update any “nullable until auth” comments in code and schemas.

---

## 4. Testing and quality

- **Auth tests**: Add tests for register (success, duplicate email), login (success, wrong password), and `/auth/me` (valid token, missing token, invalid token).
- **Protected resource tests**: After 1.x, add tests that create a resource as user A and assert user B cannot access or modify it.

---

## 5. Later / backlog

- **Refresh tokens**: Optional; add refresh token flow if you need long-lived sessions without re-login.
- **Password reset**: Forgot-password flow (email + token or link).
- **Skill-gap analysis, CV scoring, etc.**: Per README; can be built on top of the auth-wired resume and job-posting APIs.
- **Admin / roles**: If you need “list all users’ data”, introduce a simple role (e.g. `is_admin`) and use it only where needed.

---

## Suggested order

1. **Resumes** — wire auth (list, get, create/upload, update, delete).
2. **Job postings** — wire auth (list, get, create).
3. **Prep sessions** — wire auth (create, list, get, and all chat/evaluate endpoints).
4. **Security** — production JWT_SECRET and optional startup check.
5. **Tests** — auth + protected resource tests.
6. **Cleanup** — remove “until auth” comments and optional `user_id` from request schemas where no longer needed.

This keeps the backend consistent: everything that is “per-user” is actually tied to the authenticated user and inaccessible to others.
