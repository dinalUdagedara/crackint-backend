# Crackint Backend — API Overview

Base URL: **`/api/v1`** (e.g. `http://localhost:8000/api/v1`)

All successful responses use the common shape:

```json
{
  "success": true,
  "message": "...",
  "payload": { ... },
  "meta": null
}
```

List responses include **`meta`** with `page`, `page_size`, `total_pages`, `total_items`. Error responses use the same wrapper with `success: false` and `payload` containing the error detail.

---

## Health

| Method | Path | Summary |
|--------|------|--------|
| GET | `/health` | Health check |

**Response:** `{ "status": "ok" }` (or equivalent health payload)

---

## Resumes

| Method | Path | Summary |
|--------|------|--------|
| GET | `/resumes` | List all resumes (paginated, optional user filter) |
| GET | `/resumes/{resume_id}` | Get a single resume by ID |
| POST | `/resumes/extract` | Create a resume: upload PDF or paste text, extract entities, persist |
| POST | `/resumes/score` | Score a CV from file upload (PDF/image); passes to LLM vision model |
| GET | `/resumes/{resume_id}/score` | Score an existing resume using stored raw text |
| PUT | `/resumes/{resume_id}` | Update a resume: new PDF or text, re-extract, update record |
| PATCH | `/resumes/{resume_id}` | Update only selected entity fields (user-editable extracted data) |
| DELETE | `/resumes` | Delete all resumes |

### POST `/resumes/score` — Score CV from file

**Requires:** `CV_SCORING_ENABLED=true` and `OPENAI_API_KEY`. Otherwise returns `503`.

**Body:** `multipart/form-data` with `file` (PDF or image: PNG, JPEG, WebP).

**Response payload:** `score` (0–100), `breakdown` (content, structure, clarity), `suggestions` (list of strings).

**Errors:** `400` invalid file type/size. `503` if CV scoring disabled or LLM unavailable.

### GET `/resumes/{resume_id}/score` — Score existing resume

**Requires:** `CV_SCORING_ENABLED=true` and `OPENAI_API_KEY`. Uses stored `raw_text` (no vision).

**Response payload:** Same as POST `/resumes/score`.

**Errors:** `404` resume not found. `400` if resume has no raw text. `503` if CV scoring disabled.

### GET `/resumes` — List all resumes

**Query parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `user_id` | UUID | No | Filter by user ID |
| `page` | int | No | Page number (1-based). Default: 1 |
| `page_size` | int | No | Items per page (1–100). Default: 20 |

**Response payload:** Array of resume objects. Each item: `id`, `user_id`, `entities`, `raw_text`, `created_at`, `updated_at`.

**Response meta:** `page`, `page_size`, `total_pages`, `total_items`.

---

### GET `/resumes/{resume_id}` — Get resume by ID

**Path parameters:** `resume_id` (UUID)

**Response payload:** Single resume object (`id`, `user_id`, `entities`, `raw_text`, `created_at`, `updated_at`).

**Errors:** `404` if resume not found.

---

### POST `/resumes/extract` — Create resume (extract + persist)

**Body:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | One of file/text | Resume PDF (max size from `MAX_UPLOAD_SIZE_MB`) |
| `text` | string | One of file/text | Raw resume text |

**Query parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `user_id` | UUID | No | Associate resume with user (for testing until auth) |

**Response payload:** `entities` (NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE), `raw_text` (if file was uploaded).

**Errors:** `400` if both file and text sent, or neither, or invalid file type/size.

---

### PUT `/resumes/{resume_id}` — Update resume

**Path parameters:** `resume_id` (UUID)

**Body:** `multipart/form-data` — same as POST extract: **`file`** (PDF) or **`text`** (raw resume text). Send exactly one.

**Response payload:** New `entities` and `raw_text` after re-extraction.

**Errors:** `404` if resume not found. `400` if both/neither file or text, or invalid file.

---

### PATCH `/resumes/{resume_id}` — Update entity fields only

**Path parameters:** `resume_id` (UUID)

**Body:** JSON

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `entities` | object | Yes | Entity type → list of values. Only include keys you want to change. |

**Allowed entity keys:** `NAME`, `EMAIL`, `SKILL`, `OCCUPATION`, `EDUCATION`, `EXPERIENCE`.

**Example:** To change only name and skills:

```json
{
  "entities": {
    "NAME": ["Jane Doe"],
    "SKILL": ["Python", "React", "Node.js"]
  }
}
```

Omitted keys (e.g. EMAIL, OCCUPATION) are left unchanged. The given keys replace the existing list for that entity type.

**Response payload:** Full resume object after update (`id`, `user_id`, `entities`, `raw_text`, `created_at`, `updated_at`).

**Errors:** `404` if resume not found. `422` if an entity key is not one of the allowed types.

---

### DELETE `/resumes` — Delete all resumes

No parameters or body.

**Response payload:** `{ "deleted_count": N }` where N is the number of resumes deleted.

**Note:** Use with caution; this removes every resume in the database.

---

## Jobs (job descriptions)

| Method | Path | Summary |
|--------|------|--------|
| POST | `/jobs/extract` | Extract entities from a job description (PDF or text) |

### POST `/jobs/extract` — Extract job description entities

**Body:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | One of file/text | Job description PDF |
| `text` | string | One of file/text | Raw job description text |

**Response payload:** `entities`, `raw_text` (if file was uploaded).

- When **job poster NER** is loaded (`JOB_POSTER_NER_LOAD_DIR` set): entities include **JOB_TITLE**, **COMPANY**, **LOCATION**, **SALARY**, **SKILLS_REQUIRED**, **EXPERIENCE_REQUIRED**, **EDUCATION_REQUIRED**, **JOB_TYPE**.
- When fallback (resume NER) is used: entities include **NAME**, **EMAIL**, **SKILL**, **OCCUPATION**, **EDUCATION**, **EXPERIENCE**.

**Errors:** `400` if both file and text sent, or neither, or invalid file type/size.

---

## Sessions (prep)

| Method | Path | Summary |
|--------|------|--------|
| POST | `/sessions` | Create a prep session (user_id, resume_id, job_posting_id, mode: TARGETED/QUICK_PRACTICE/TUTOR_CHAT) |
| GET | `/sessions` | List prep sessions |
| GET | `/sessions/{session_id}` | Get session by ID (no messages) |
| DELETE | `/sessions/{session_id}` | Delete session by ID (messages deleted via cascade) |
| GET | `/sessions/{session_id}/with-messages` | Get session with messages |
| GET | `/sessions/{session_id}/messages` | List messages in session |
| POST | `/sessions/{session_id}/messages` | Append a message (QUESTION, ANSWER, or FEEDBACK) |
| POST | `/sessions/{session_id}/next-question` | Generate next interview question (requires Session Q&A agent) |
| POST | `/sessions/{session_id}/evaluate-answer` | Evaluate candidate's answer; store feedback (requires Session Q&A agent) |

### POST `/sessions/{session_id}/next-question`

**Requires:** `SESSION_QA_AGENT_ENABLED=true` and `OPENAI_API_KEY` set. Otherwise returns `503`.

**Body (optional):** `{ "question_type": "technical" | "behavioral" | "system_design", "role_level": "INTERN" | "ASE" | "SSE" | "OTHER", "prefer_difficulty": "easy" | "medium" | "hard" }`. Default `role_level` is ASE. If `prefer_difficulty` is set, the next question prefers that difficulty; otherwise the session difficulty curve is used.

**Response payload:** `question`, `difficulty`, `question_type`, `message_id` (the stored ASSISTANT QUESTION message).

**Errors:** `404` session not found. `503` if Session Q&A agent disabled or LLM unavailable.

### POST `/sessions/{session_id}/evaluate-answer`

**Requires:** Session Q&A agent enabled. Evaluates against the **last QUESTION** message in the session.

**Body:** `{ "answer": "candidate's answer text", "prefer_difficulty": "easy" | "medium" | "hard" (optional) }`. When the user skips and a next question is returned, `prefer_difficulty` can override the session curve.

**Response payload:** `feedback`, `score` (0–100), `dimension_tags`, `message_id` (the stored ASSISTANT FEEDBACK message).

**Errors:** `400` if no question in session. `404` session not found. `503` if agent disabled or LLM unavailable.

---

## Match (skill-gap)

| Method | Path | Summary |
|--------|------|--------|
| POST | `/match/skill-gap` | Compare resume vs job posting; return gaps, suggestions, alerts |

### POST `/match/skill-gap`

**Body:** `{ "resume_id": "uuid", "job_posting_id": "uuid" }`

**Response payload:** `missing_skills`, `weak_experience`, `weak_education`, `suggestions`, `severity` (low|medium|high), `alerts` (array of `{ type, message, severity }`).

**Errors:** `404` if resume or job posting not found or not owned by current user.

---

## Users

| Method | Path | Summary |
|--------|------|--------|
| GET | `/users/me/readiness` | Combined readiness (CV score + session avg + gap penalty) |
| GET | `/users/me/readiness/summary` | Readiness summary + aggregates for dashboard |
| GET | `/users/me/readiness/trend` | Recent session readiness scores for trend charts |
| GET | `/users/me/home-summary` | Home/dashboard summary cards (Jump Back In, Refine CV, Readiness Tracker) |

### GET `/users/me/readiness`

**Query parameters:** `resume_id` (optional), `job_posting_id` (optional). If both provided, CV score and gap analysis are included.

**Response payload:** `combined_score`, `cv_score`, `session_avg`, `gap_severity`, `trend`.

---

### GET `/users/me/readiness/summary`

**Query parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `resume_id` | UUID | No | Optional resume ID for CV score and gap analysis. |
| `job_posting_id` | UUID | No | Optional job posting ID for gap analysis (requires resume_id). |
| `last_n_sessions` | int | No | Number of recent sessions to include in aggregates (default 5, max 50). |

**Response payload:** Dashboard-oriented readiness summary:

```json
{
  "combined_score": 82.5,
  "trend": "stable",
  "cv_score": 78.0,
  "session_avg": 85.3,
  "gap_severity": "medium",
  "session_count_total": 14,
  "session_count_with_scores": 9,
  "last_n_sessions": 5,
  "difficulty_distribution": {
    "easy": 4,
    "medium": 7,
    "hard": 2
  }
}
```

---

### GET `/users/me/readiness/trend`

**Query parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `limit` | int | No | Max number of recent sessions to return (default 10, max 100). |

**Response payload:** Array of recent sessions (newest first), e.g.:

```json
[
  {
    "session_id": "uuid",
    "created_at": "2026-03-12T10:15:00",
    "mode": "TARGETED",
    "readiness_score": 84.0,
    "title": "ASE Backend – Python role"
  },
  {
    "session_id": "uuid",
    "created_at": "2026-03-10T17:30:00",
    "mode": "QUICK_PRACTICE",
    "readiness_score": 79.5,
    "title": null
  }
]
```

---

### GET `/users/me/home-summary`

**When to use:** Summary view on the home/dashboard. Returns three cards with actionable items so the frontend can render "Jump Back In", "Refine CV", and "Readiness Tracker" and link each item to sessions, resumes, or job postings.

**Auth:** Required (same as other `/users/me/*`).

**Response payload:** `payload.cards` is an array of exactly three cards (fixed order):

| Card `id` | `title` | `icon` | Contents |
|-----------|--------|--------|----------|
| `jump_back_in` | Jump Back In | `messages` | Recent sessions: `title`, `session_id`, `href` |
| `refine_cv` | Refine CV | `sparkles` | Skill-gap suggestions: `title`, optional `resume_id`, `job_posting_id`, `href` |
| `readiness_tracker` | Readiness Tracker | `shield` | Readiness insights: `title`, `session_id`/`job_posting_id`, `href`; plus a "Start practice" item with `action_type: "start_session"` |

Each **item** in `cards[].items` has:

- **`title`** (string, required)
- **`description`** (string, optional)
- **`href`** (string, optional) — e.g. `/sessions/{id}`, `/resumes/{id}`, `/job-postings/{id}`
- **`session_id`**, **`resume_id`**, **`job_posting_id`** (strings, optional) — for frontend route building
- **`action_type`** (string, optional) — e.g. `start_session`, `open_cv`, `open_job`

Example (minimal):

```json
{
  "success": true,
  "payload": {
    "cards": [
      {
        "id": "jump_back_in",
        "title": "Jump Back In",
        "icon": "messages",
        "items": [
          { "title": "Practice session", "session_id": "uuid", "href": "/sessions/uuid" }
        ]
      },
      {
        "id": "refine_cv",
        "title": "Refine CV",
        "icon": "sparkles",
        "items": [
          { "title": "Consider adding or highlighting these skills: Docker.", "resume_id": "uuid", "job_posting_id": "uuid", "href": "/resumes/uuid" }
        ]
      },
      {
        "id": "readiness_tracker",
        "title": "Readiness Tracker",
        "icon": "shield",
        "items": [
          { "title": "Readiness for Frontend Engineer (Shopify) is 72%", "job_posting_id": "uuid", "href": "/job-postings/uuid" },
          { "title": "Start practice", "action_type": "start_session" }
        ]
      }
    ]
  }
}
```

---

## Interactive docs

- **Swagger UI:** [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **ReDoc:** [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
