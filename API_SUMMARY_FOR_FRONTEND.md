# Crackint Backend API — Summary for Frontend

**Base URL:** `http://localhost:8000` (or your deployed URL)  
**API prefix:** `/api/v1`

All JSON responses use this wrapper:

```ts
interface CommonResponse<T> {
  success: boolean;
  message: string;
  payload: T | null;
  meta?: { page: number; page_size: number; total_pages: number; total_items: number };
}
```

---

## 1. Root

**GET /**  
No auth.

**Response (JSON):**
```json
{
  "message": "Crackint Backend API",
  "docs": "/api/v1/docs",
  "health": "/api/v1/health"
}
```

---

## 2. Health check

**GET /api/v1/health**  
No auth. Use for readiness/health checks.

**Response (JSON):**
```json
{ "status": "ok" }
```

---

## 3. Resume entity extraction

**POST /api/v1/resumes/extract**  
No auth.

Extract entities (NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE) from a resume. Send **either** a PDF file **or** raw text, not both.

**Request:**
- **Content-Type:** `multipart/form-data`
- **Body (choose one):**
  - **file** (optional): PDF file (field name `file`)
  - **text** (optional): string, raw resume text (field name `text`)

**Success response (200):**
```ts
CommonResponse<{
  entities: Record<string, string[]>;  // NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE
  raw_text: string | null;            // present when client sent file; null when client sent text
}>
```
Example:
```json
{
  "success": true,
  "message": "Entities extracted successfully",
  "payload": {
    "entities": {
      "NAME": ["John Doe"],
      "EMAIL": ["john@example.com"],
      "SKILL": ["Python", "FastAPI"],
      "OCCUPATION": [],
      "EDUCATION": ["BSc Computer Science"],
      "EXPERIENCE": ["Software Engineer at Acme"]
    },
    "raw_text": "Full extracted text from PDF..."
  }
}
```

**Error responses:**
- **400** — Send either `file` or `text`, not both; or both missing.
- **400** — Only PDF allowed (`content-type: application/pdf`).
- **400** — File too large (max default 10 MB).

**Frontend example (fetch):**
```ts
// Option A: Upload PDF
const formData = new FormData();
formData.append("file", pdfFile);
const res = await fetch(`${baseUrl}/api/v1/resumes/extract`, {
  method: "POST",
  body: formData,
});

// Option B: Send raw text
const formData = new FormData();
formData.append("text", resumeText);
const res = await fetch(`${baseUrl}/api/v1/resumes/extract`, {
  method: "POST",
  body: formData,
});
```

---

## 4. Job description entity extraction

**POST /api/v1/jobs/extract**  
No auth.

Extract entities from a job description (PDF or text). With job-poster NER: e.g. JOB_TITLE, COMPANY, SKILLS_REQUIRED, SALARY. Fallback uses resume-style entities: SKILL, OCCUPATION, EDUCATION, EXPERIENCE.

**Request:**
- **Content-Type:** `multipart/form-data`
- **Body (choose one):**
  - **file** (optional): PDF file (field name `file`)
  - **text** (optional): string, raw job description (field name `text`)

**Success response (200):**
```ts
CommonResponse<{
  entities: Record<string, string[]>;  // keys depend on NER (job poster vs resume fallback)
  raw_text: string | null;
}>
```

**Error responses:** Same as resume extract (400 for both missing, wrong type, or file too large).

**Frontend example (fetch):**
```ts
const formData = new FormData();
formData.append("file", jobPdfFile);  // or formData.append("text", jobDescriptionText);
const res = await fetch(`${baseUrl}/api/v1/jobs/extract`, {
  method: "POST",
  body: formData,
});
```

---

## Quick reference

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/` | Root info |
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/resumes/extract` | Extract resume entities (file or text) |
| POST | `/api/v1/jobs/extract` | Extract job description entities (file or text) |

**Docs (Swagger):** `GET /api/v1/docs`  
**ReDoc:** `GET /api/v1/redoc`
