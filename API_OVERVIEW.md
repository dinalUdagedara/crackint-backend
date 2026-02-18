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
| PUT | `/resumes/{resume_id}` | Update a resume: new PDF or text, re-extract, update record |
| PATCH | `/resumes/{resume_id}` | Update only selected entity fields (user-editable extracted data) |
| DELETE | `/resumes` | Delete all resumes |

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
| POST | `/sessions` | Create a prep session (user_id, resume_id, job_posting_id, mode) |
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

**Body (optional):** `{ "question_type": "technical" | "behavioral" | "system_design", "role_level": "INTERN" | "ASE" | "SSE" | "OTHER" }`. Default `role_level` is ASE.

**Response payload:** `question`, `difficulty`, `question_type`, `message_id` (the stored ASSISTANT QUESTION message).

**Errors:** `404` session not found. `503` if Session Q&A agent disabled or LLM unavailable.

### POST `/sessions/{session_id}/evaluate-answer`

**Requires:** Session Q&A agent enabled. Evaluates against the **last QUESTION** message in the session.

**Body:** `{ "answer": "candidate's answer text" }`.

**Response payload:** `feedback`, `score` (0–100), `dimension_tags`, `message_id` (the stored ASSISTANT FEEDBACK message).

**Errors:** `400` if no question in session. `404` session not found. `503` if agent disabled or LLM unavailable.

---

## Interactive docs

- **Swagger UI:** [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **ReDoc:** [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
