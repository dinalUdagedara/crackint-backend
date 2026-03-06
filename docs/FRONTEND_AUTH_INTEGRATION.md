# Frontend integration: Authentication and resource ownership

Use this doc when updating the frontend to work with the backend after auth and resource ownership were wired. Base URL and API prefix below; all endpoints use the same response wrapper.

---

## Base URL and response shape

- **Base URL**: `http://localhost:8000` (or your backend origin).
- **API prefix**: `/api/v1` — all API routes live under `/api/v1/...`.
- **Standard response**: Every API returns a JSON object:
  ```json
  {
    "success": true | false,
    "message": "string",
    "payload": <data or null>,
    "meta": { "page", "page_size", "total_pages", "total_items" }  // only on paginated list endpoints
  }
  ```
  Use `payload` for the actual data; check `success` and `message` for errors or user feedback.

---

## Authentication flow

### 1. Register

- **Endpoint**: `POST /api/v1/auth/register`
- **Headers**: `Content-Type: application/json`
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "min8chars",
    "name": "Display Name"
  }
  ```
- **Response**: `201` with `payload` = user object (no token). User must then log in.
- **Errors**: `400` if email already registered (check `detail` in error response).

### 2. Login

- **Endpoint**: `POST /api/v1/auth/login`
- **Headers**: `Content-Type: application/json`
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "password"
  }
  ```
- **Response**: `200` with `payload`:
  ```json
  {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "name": "Display Name",
      "created_at": "ISO8601"
    }
  }
  ```
- **Frontend**: Store `access_token` (e.g. in memory, localStorage, or secure storage). Send it on every request to protected endpoints.

### 3. Sending the token (protected endpoints)

- **Header**: `Authorization: Bearer <access_token>`
- **Example**: `Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
- If the token is missing, expired, or invalid, the backend returns **401** with a body like `{"detail": "Not authenticated"}` or `"Invalid or expired token"`. Redirect to login and clear stored token.

### 4. Current user (optional)

- **Endpoint**: `GET /api/v1/auth/me`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response**: `200` with `payload` = same user shape as login (`id`, `email`, `name`, `created_at`). Use this to restore session on app load or to show the logged-in user.

---

## Endpoints that now require authentication

All of the following **require** `Authorization: Bearer <access_token>`. Without it they return **401**.

| Area | Endpoints |
|------|-----------|
| **Resumes** | `GET /api/v1/resumes`, `GET /api/v1/resumes/{id}`, `POST /api/v1/resumes/extract`, `PUT /api/v1/resumes/{id}`, `PATCH /api/v1/resumes/{id}`, `DELETE /api/v1/resumes` |
| **Job postings** | `GET /api/v1/job-postings`, `GET /api/v1/job-postings/{id}`, `POST /api/v1/job-postings` |
| **Prep sessions** | `POST /api/v1/sessions`, `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `DELETE /api/v1/sessions/{id}`, `GET /api/v1/sessions/{id}/messages`, `POST /api/v1/sessions/{id}/messages`, `GET /api/v1/sessions/{id}/with-messages`, `POST /api/v1/sessions/{id}/next-question`, `POST /api/v1/sessions/{id}/chat`, `POST /api/v1/sessions/{id}/send`, `POST /api/v1/sessions/{id}/evaluate-answer` |

**Resumes**: `POST /api/v1/resumes/preview-extract` stays **public** (no auth) so you can preview extraction without logging in if you want.

---

## Request/response changes for the frontend

### Resumes

- **List** `GET /api/v1/resumes`
  - **Removed**: Query param `user_id`. Do not send it.
  - **Behavior**: Returns only the **current user’s** resumes (same as before when you passed that user’s `user_id`). Pagination params `page` and `page_size` unchanged.
- **Get by ID** `GET /api/v1/resumes/{id}`
  - **Behavior**: Returns **404** if the resume exists but belongs to another user (no data leak). Treat 404 as “not found or no access”.
- **Create (extract + save)** `POST /api/v1/resumes/extract`
  - **Removed**: Query param `user_id`. Do not send it.
  - **Behavior**: New resume is always created for the current user.
- **Update** `PUT /api/v1/resumes/{id}`, **Patch** `PATCH /api/v1/resumes/{id}`
  - **Behavior**: **404** if the resume is not owned by the current user.
- **Delete all** `DELETE /api/v1/resumes`
  - **Behavior**: Deletes only the **current user’s** resumes.

### Job postings

- **List** `GET /api/v1/job-postings`
  - **Removed**: Query param `user_id`. Do not send it.
  - **Behavior**: Returns only the current user’s job postings.
- **Get by ID** `GET /api/v1/job-postings/{id}`
  - **Behavior**: **404** if the job posting is not owned by the current user.
- **Create** `POST /api/v1/job-postings`
  - **Body**: You can still send `user_id` in the JSON for backward compatibility; the backend **ignores** it and sets the owner from the token. Easiest: omit `user_id` in the request body.

### Prep sessions

- **Create** `POST /api/v1/sessions`
  - **Body**: You can still send `user_id`; the backend **ignores** it and sets the owner from the token. Easiest: omit `user_id`.
  - **Behavior**: New session is always for the current user.
- **List** `GET /api/v1/sessions`
  - **Behavior**: Returns only the current user’s sessions (no `user_id` filter param).
- **All endpoints under** `GET/POST/DELETE /api/v1/sessions/{id}/...`
  - **Behavior**: **404** if the session does not exist or is not owned by the current user. No need to send `user_id` anywhere.

---

## Summary checklist for the frontend

1. **Auth**
   - After login, store `access_token` from `POST /api/v1/auth/login` response (`payload.access_token`).
   - On app load, optionally call `GET /api/v1/auth/me` with the stored token to restore the user; on 401, clear token and show login.
   - For all resume, job-posting, and session endpoints (except resume preview-extract), send `Authorization: Bearer <access_token>`.

2. **Remove or stop using**
   - `user_id` query param on list resumes and list job postings.
   - `user_id` query param on resume extract (upload).
   - `user_id` in request body for create job posting and create prep session (optional to remove; backend ignores it).

3. **Errors**
   - **401**: Token missing/invalid/expired → clear token, redirect to login.
   - **404** on get/update/delete: treat as “resource not found or no access”; do not show another user’s data.

4. **Data scope**
   - Lists (resumes, job postings, sessions) are always scoped to the current user. No need to filter by `user_id` on the client for these.

Paste this doc into your frontend project (or into Cursor) when updating API calls and auth so the client stays in sync with the backend.
