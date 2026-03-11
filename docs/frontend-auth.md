# Frontend auth integration

Guide for integrating the Crackint backend auth (register, login, JWT) from the frontend. Use this with NextAuth (CredentialsProvider) or any client that calls the backend API.

## Base URL and config

- **Auth base path:** `{API_BASE_URL}/auth`
- **Example:** If the backend is at `http://localhost:8000` and `API_PREFIX` is `/api/v1`, then auth base is `http://localhost:8000/api/v1/auth`.

Recommended env in the frontend:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Response wrapper

All auth endpoints return the same envelope:

```ts
interface CommonResponse<T> {
  success: boolean;
  message: string;
  payload: T | null;
  meta?: { page: number; page_size: number; total_pages: number; total_items: number };
}
```

Auth responses use `payload` for the actual data; `meta` is not used for auth.

## Types (TypeScript)

```ts
// User object returned by register, login, and me
interface User {
  id: string;       // UUID
  email: string;
  name: string;
  created_at: string; // ISO 8601
}

// Register request
interface RegisterBody {
  email: string;
  password: string;
  name: string;
}

// Login request
interface LoginBody {
  email: string;
  password: string;
}

// Login response payload (inside CommonResponse.payload)
interface LoginPayload {
  access_token: string;
  token_type: "bearer";
  user: User;
}
```

## Endpoints

### POST /auth/register

Create a new user. Does not return a token; call login after a successful register if you want to sign the user in immediately.

**Request**

- **URL:** `POST {API_BASE_URL}/auth/register`
- **Body:** `RegisterBody`
- **Headers:** `Content-Type: application/json`

**Success (201)**

- **Body:** `CommonResponse<User>`
- Use `response.payload` for the new user (id, email, name, created_at).

**Errors**

- **400:** Email already registered. Body: `{ detail: "Email already registered" }`
- **422:** Validation error (e.g. invalid email, password &lt; 8 chars). Body: `{ detail: Array<{ loc, msg, type }> }` or similar.

**Example (fetch)**

```ts
const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/register`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password, name }),
});
const data = await res.json();
if (!res.ok) throw new Error(data.detail ?? "Registration failed");
// data.payload is User
```

---

### POST /auth/login

Authenticate and get a JWT and user. This is what NextAuth CredentialsProvider should call.

**Request**

- **URL:** `POST {API_BASE_URL}/auth/login`
- **Body:** `LoginBody`
- **Headers:** `Content-Type: application/json`

**Success (200)**

- **Body:** `CommonResponse<LoginPayload>`
- `payload.access_token`: JWT to send in `Authorization: Bearer <access_token>` on later requests.
- `payload.user`: `User` (id, email, name, created_at).

**Errors**

- **401:** Invalid email or password. Body: `{ detail: "Invalid email or password" }`
- **422:** Validation error (e.g. invalid email format).

**Example (fetch)**

```ts
const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
});
const data = await res.json();
if (!res.ok) throw new Error(data.detail ?? "Login failed");
const { access_token, user } = data.payload;
// Store access_token (e.g. in NextAuth session) and use for API calls
```

---

### GET /auth/me

Return the current user. Requires a valid JWT.

**Request**

- **URL:** `GET {API_BASE_URL}/auth/me`
- **Headers:** `Authorization: Bearer <access_token>`

**Success (200)**

- **Body:** `CommonResponse<User>`
- `payload` is the current user.

**Errors**

- **401:** Missing or invalid token. Body: `{ detail: "Not authenticated" }` or similar.

**Example (fetch)**

```ts
const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/me`, {
  headers: { Authorization: `Bearer ${accessToken}` },
});
const data = await res.json();
if (!res.ok) throw new Error(data.detail ?? "Unauthorized");
// data.payload is User
```

## Sending the token to the backend

For any protected backend route (e.g. sessions, resumes, job-postings once they require auth):

- Add header: **`Authorization: Bearer <access_token>`**
- Get `access_token` from your auth state (e.g. NextAuth session).

**Client component (e.g. with useSession):**

```ts
const { data: session } = useSession();
const token = session?.accessToken; // or wherever you store the backend JWT

const res = await fetch(`${API_URL}/sessions`, {
  headers: token ? { Authorization: `Bearer ${token}` } : {},
  // ...
});
```

**Server component / API route / server action:**

```ts
const session = await getServerSession(authOptions);
const token = session?.accessToken;

const res = await fetch(`${API_URL}/sessions`, {
  headers: token ? { Authorization: `Bearer ${token}` } : {},
  // ...
});
```

## NextAuth (CredentialsProvider) example

1. Call the backend login from the `authorize` callback.
2. Return the user and `access_token` so they can be stored in the JWT/session.
3. In the JWT and session callbacks, put `access_token` on the session so the frontend can send it to the backend.

**Minimal flow:**

```ts
// app/api/auth/[...nextauth]/route.ts
import NextAuth from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

export const authOptions = {
  providers: [
    CredentialsProvider({
      name: "credentials",
      credentials: { email: { label: "Email" }, password: { label: "Password" } },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;
        const res = await fetch(`${API_URL}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
        });
        if (!res.ok) return null;
        const data = await res.json();
        const { access_token, user } = data.payload;
        return { id: user.id, email: user.email, name: user.name, accessToken: access_token };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user?.accessToken) token.accessToken = user.accessToken;
      return token;
    },
    async session({ session, token }) {
      if (session.user) session.accessToken = token.accessToken;
      return session;
    },
  },
  // ...
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
```

Extend the `Session` type so `session.accessToken` is typed:

```ts
declare module "next-auth" {
  interface Session {
    accessToken?: string;
  }
}
```

Then use `session.accessToken` in fetch calls to the backend as `Authorization: Bearer <accessToken>`.

## Validation rules (backend)

- **email:** Valid email format (backend uses Pydantic `EmailStr`).
- **password (register):** Minimum length 8.
- **name:** At least one character.

Returned **422** bodies for validation errors follow FastAPI’s format (e.g. `detail` as an array of error objects). You can surface the first message or map fields for inline form errors.

## Summary

| Action   | Method | URL                    | Body           | Headers              |
|----------|--------|------------------------|----------------|----------------------|
| Register | POST   | `.../auth/register`    | email, password, name | Content-Type: application/json |
| Login    | POST   | `.../auth/login`       | email, password       | Content-Type: application/json |
| Me       | GET    | `.../auth/me`          | —                      | Authorization: Bearer &lt;token&gt; |

All success responses are `CommonResponse<T>`; use `payload` for the data. Store `payload.access_token` from login and send it as `Authorization: Bearer <access_token>` on every request to protected backend routes.
