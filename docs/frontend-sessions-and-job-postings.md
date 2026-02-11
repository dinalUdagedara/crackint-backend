## Frontend Guide: Job Postings & Prep Sessions

Last updated: Feb 11, 2026

This document explains how the frontend should talk to the backend for:

- Saving **job postings** (from `/jobs/extract` output)
- Creating and listing **prep sessions**
- Sending and reading **chat-style messages** in a session

Base API prefix: `/api/v1`

---

## 1. Job Posting APIs

### 1.1 List job postings

- **Endpoint**: `GET /api/v1/job-postings`
- **Query params**:
  - `page` (default `1`)
  - `page_size` (default `20`, max `100`)
  - `user_id` (optional, UUID) – to filter by owner

**Response shape** (wrapped in `CommonResponse`):

```json
{
  "success": true,
  "message": "Job postings retrieved successfully",
  "payload": [
    {
      "id": "uuid",
      "user_id": "uuid or null",
      "entities": {
        "JOB_TITLE": ["..."],
        "COMPANY": ["..."],
        "LOCATION": ["..."]
      },
      "raw_text": "full job description or null",
      "location": "normalized location or null",
      "deadline": "2026-02-11T00:00:00" ,
      "created_at": "2026-02-11T00:00:00",
      "updated_at": "2026-02-11T00:00:00"
    }
  ],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "total_items": 0
  }
}
```

### 1.2 Get a single job posting

- **Endpoint**: `GET /api/v1/job-postings/{id}`

Returns the same `JobPostingListItem` payload as above for a single record.

### 1.3 Create a job posting (from `/jobs/extract`)

Typical flow:

1. Frontend sends job description (file or text) to:
   - `POST /api/v1/jobs/extract?validate=true`
2. Backend returns `JobExtractResponse`:
   - `entities`: extracted job entities
   - `raw_text`: extracted text (if file upload)
3. Frontend **creates** a job posting record:
   - `POST /api/v1/job-postings`

**Request body** (`JobPostingCreate`):

```json
{
  "user_id": "uuid-or-null",
  "entities": {
    "JOB_TITLE": ["Software Engineer"],
    "COMPANY": ["Example Corp"],
    "LOCATION": ["Colombo"],
    "SKILLS_REQUIRED": ["Python", "FastAPI"]
  },
  "raw_text": "Full job description text here...",
  "location": "Colombo, Sri Lanka",
  "deadline": "2026-03-01T00:00:00"
}
```

**Response**:

```json
{
  "success": true,
  "message": "Job posting created successfully",
  "payload": {
    "id": "uuid",
    "user_id": "uuid-or-null",
    "entities": { "...": ["..."] },
    "raw_text": "Full job description text here...",
    "location": "Colombo, Sri Lanka",
    "deadline": "2026-03-01T00:00:00",
    "created_at": "2026-02-11T00:00:00",
    "updated_at": "2026-02-11T00:00:00"
  }
}
```

---

## 2. Prep Session APIs

Prep sessions represent a **chat-based interview prep run** (user + resume + job posting).

### 2.1 Create a prep session

- **Endpoint**: `POST /api/v1/sessions`

**Request body** (`PrepSessionCreate`):

```json
{
  "user_id": "uuid-or-null",
  "resume_id": "uuid-or-null",
  "job_posting_id": "uuid-or-null",
  "mode": "TARGETED"  // or "QUICK_PRACTICE"
}
```

Notes:

- `user_id`, `resume_id`, `job_posting_id` are nullable for now (no auth yet).
- For the **full targeted flow**, pass all three:
  - `user_id` (when you have it)
  - `resume_id` from `/api/v1/resumes` (or `/resumes/extract`)
  - `job_posting_id` from `/api/v1/job-postings`

**Response** (`PrepSessionRead`):

```json
{
  "success": true,
  "message": "Prep session created successfully",
  "payload": {
    "id": "uuid",
    "user_id": "uuid-or-null",
    "resume_id": "uuid-or-null",
    "job_posting_id": "uuid-or-null",
    "mode": "TARGETED",
    "status": "ACTIVE",
    "readiness_score": null,
    "summary": {},
    "created_at": "2026-02-11T00:00:00",
    "updated_at": "2026-02-11T00:00:00"
  }
}
```

### 2.2 List prep sessions

- **Endpoint**: `GET /api/v1/sessions`

Returns `CommonResponse` with `payload` as `PrepSessionRead[]` (no messages).

### 2.3 Get a single session (no messages)

- **Endpoint**: `GET /api/v1/sessions/{session_id}`

Returns `CommonResponse<PrepSessionRead>`.

---

## 3. Session Messages (Chat)

Messages represent the **chat history** inside a prep session.

### 3.1 Append a message to a session

- **Endpoint**: `POST /api/v1/sessions/{session_id}/messages`

**Request body** (`MessageCreate`):

```json
{
  "sender": "USER",         // or "ASSISTANT"
  "type": "QUESTION",       // "QUESTION" | "ANSWER" | "FEEDBACK"
  "content": "User or assistant text here",
  "metadata": {
    "score": "85",
    "dimension": "technical"
  }
}
```

**Response** (`MessageRead`):

```json
{
  "success": true,
  "message": "Message appended successfully",
  "payload": {
    "id": "uuid",
    "session_id": "uuid",
    "sender": "USER",
    "type": "QUESTION",
    "content": "User or assistant text here",
    "metadata": {
      "score": "85",
      "dimension": "technical"
    },
    "created_at": "2026-02-11T00:00:00",
    "updated_at": "2026-02-11T00:00:00"
  }
}
```

### 3.2 List messages in a session

- **Endpoint**: `GET /api/v1/sessions/{session_id}/messages`

Returns `CommonResponse<List<MessageRead>>` ordered by `created_at` ascending.

### 3.3 Get session with messages (one-shot)

- **Endpoint**: `GET /api/v1/sessions/{session_id}/with-messages`

Returns:

```json
{
  "success": true,
  "message": "Prep session with messages retrieved successfully",
  "payload": {
    "id": "uuid",
    "user_id": "uuid-or-null",
    "resume_id": "uuid-or-null",
    "job_posting_id": "uuid-or-null",
    "mode": "TARGETED",
    "status": "ACTIVE",
    "readiness_score": null,
    "summary": {},
    "created_at": "2026-02-11T00:00:00",
    "updated_at": "2026-02-11T00:00:00",
    "messages": [
      {
        "id": "uuid",
        "session_id": "uuid",
        "sender": "USER",
        "type": "QUESTION",
        "content": "First question",
        "metadata": {},
        "created_at": "2026-02-11T00:00:00",
        "updated_at": "2026-02-11T00:00:00"
      }
    ]
  }
}
```

---

## 4. Recommended frontend flow (MVP)

1. **Resume parsing**
   - `POST /api/v1/resumes/extract?validate=true` → get `entities` + `raw_text`.
   - Backend already persists a `Resume` row; frontend can read list via `GET /api/v1/resumes`.
2. **Job parsing**
   - `POST /api/v1/jobs/extract?validate=true` → get `entities` + `raw_text`.
   - `POST /api/v1/job-postings` → save a `JobPosting` and store its `id`.
3. **Start a prep session**
   - `POST /api/v1/sessions` with `user_id` (if available), `resume_id`, `job_posting_id`, `mode="TARGETED"`.
4. **Run chat-style interview**
   - For each turn:
     - Frontend sends user message via `POST /api/v1/sessions/{session_id}/messages`.
     - (Later) another endpoint will generate assistant questions/feedback based on LLM.
   - Frontend shows chat using:
     - `GET /api/v1/sessions/{session_id}/with-messages` or
     - `GET /api/v1/sessions/{session_id}` + `GET /api/v1/sessions/{session_id}/messages`.

You can now safely start frontend work using these endpoints; future features (LLM question generation, scoring, readiness) will plug into the same `sessions` and `messages` APIs without breaking them.

