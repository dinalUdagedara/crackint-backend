# Auth API

JWT-based authentication: register, login, and current user. Use the returned `access_token` in the `Authorization` header for protected routes.

Base path: `{API_PREFIX}/auth` (e.g. `/api/v1/auth`).

## Endpoints

### POST /auth/register

Create a new user.

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "name": "Display Name"
}
```

- `email`: valid email, must be unique
- `password`: min 8 characters
- `name`: non-empty string

**Response (201):** `CommonResponse` with `payload` = user object (id, email, name, created_at). No token; client should call login.

**Errors:** 400 if email already registered.

---

### POST /auth/login

Authenticate and receive a JWT.

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response (200):** `CommonResponse` with `payload`:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "name": "Display Name",
    "created_at": "2026-02-18T..."
  }
}
```

Use `payload.access_token` in subsequent requests.

**Errors:** 401 if email or password is invalid.

---

### GET /auth/me

Return the authenticated user. Requires a valid JWT.

**Headers:**

```
Authorization: Bearer <access_token>
```

**Response (200):** `CommonResponse` with `payload` = user object (id, email, name, created_at).

**Errors:** 401 if missing or invalid token.

---

## Using the token (frontend / NextAuth)

1. After login, store `payload.access_token` (e.g. in NextAuth session).
2. For every request to the backend, set header: `Authorization: Bearer <access_token>`.
3. Protected routes use this token to resolve the current user.

Example:

```bash
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" https://api.example.com/api/v1/auth/me
```
