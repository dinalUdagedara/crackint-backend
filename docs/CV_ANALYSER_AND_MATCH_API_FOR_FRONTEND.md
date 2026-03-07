# CV Analyser & Match API — Frontend Integration Guide

This document describes the new CV analyser, skill-gap, and readiness APIs added to the Crackint backend. Use it when integrating these features into the frontend.

---

## Overview

Four new feature areas were implemented:

1. **CV Scoring** — Rate CV strength (0–100) by passing PDF/image directly to LLM vision, or using stored raw text
2. **Skill-Gap Analysis** — Compare resume vs job posting; missing skills, weak experience/education, suggestions
3. **CV–Job Suitability Alerts** — Structured warnings when job demands skills missing from CV
4. **Combined Readiness** — Aggregate score combining CV score, session performance, and gap severity

---

## Base URL & Auth

- **Base URL:** `http://localhost:8000` (or your backend origin)
- **API prefix:** `/api/v1`
- **Auth:** All endpoints require JWT. Send header:
  ```
  Authorization: Bearer <access_token>
  ```
- **Response shape:** Standard wrapper:
  ```json
  {
    "success": true,
    "message": "...",
    "payload": { ... },
    "meta": null
  }
  ```

---

## 1. CV Scoring

### POST `/api/v1/resumes/score`

**Primary flow.** Upload a CV file (PDF or image) and get an LLM-based score.

**Request:** `multipart/form-data`

| Field | Type   | Required | Description                                  |
|-------|--------|----------|----------------------------------------------|
| `file`| File   | Yes      | Resume PDF or image (PNG, JPEG, WebP)        |

**Response `payload`:**
```json
{
  "score": 78.5,
  "breakdown": {
    "content": 80,
    "structure": 75,
    "clarity": 82
  },
  "suggestions": [
    "Add metrics to quantify your impact in experience descriptions.",
    "Include a brief summary or objective at the top."
  ]
}
```

**Errors:** `503` if CV scoring disabled (set `CV_SCORING_ENABLED=true` and `OPENAI_API_KEY` in backend `.env`).

**Example (fetch):**
```typescript
const formData = new FormData();
formData.append("file", file); // File from input

const res = await fetch(`${API_BASE}/resumes/score`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
  body: formData,
});
const { success, payload } = await res.json();
if (success) {
  console.log("CV Score:", payload.score, payload.suggestions);
}
```

---

### GET `/api/v1/resumes/{resume_id}/score`

Score an **existing** resume using stored raw text (no file upload). Use when the user already has a resume in the system.

**Response `payload`:** Same shape as POST `/resumes/score`.

**Errors:** `404` resume not found. `400` if resume has no raw text. `503` if CV scoring disabled.

**Example:**
```typescript
const res = await fetch(`${API_BASE}/resumes/${resumeId}/score`, {
  headers: { Authorization: `Bearer ${accessToken}` },
});
const { success, payload } = await res.json();
```

---

## 2. Skill-Gap Analysis

### POST `/api/v1/match/skill-gap`

Compare a resume with a job posting and get gaps, suggestions, and alerts.

**Request body (JSON):**
```json
{
  "resume_id": "uuid-string",
  "job_posting_id": "uuid-string"
}
```

**Response `payload`:**
```json
{
  "missing_skills": ["AWS", "Kubernetes", "Docker"],
  "weak_experience": true,
  "weak_experience_message": "Job may require ~3+ years; resume suggests ~2.",
  "weak_education": false,
  "weak_education_message": null,
  "suggestions": [
    "Consider adding or highlighting these skills: AWS, Kubernetes, Docker.",
    "Experience: Job may require ~3+ years; resume suggests ~2."
  ],
  "severity": "high",
  "alerts": [
    {
      "type": "missing_skill",
      "message": "Missing 3 required skill(s): AWS, Kubernetes, Docker",
      "severity": "high"
    },
    {
      "type": "weak_experience",
      "message": "Job may require ~3+ years; resume suggests ~2.",
      "severity": "medium"
    }
  ]
}
```

- `severity`: `"low"` | `"medium"` | `"high"`
- `alerts[].type`: `"missing_skill"` | `"weak_experience"` | `"weak_education"`

**Example:**
```typescript
const res = await fetch(`${API_BASE}/match/skill-gap`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${accessToken}`,
  },
  body: JSON.stringify({ resume_id: resumeId, job_posting_id: jobPostingId }),
});
const { success, payload } = await res.json();
if (success) {
  // Show payload.alerts in UI; payload.missing_skills for suggestions
}
```

---

## 3. Combined Readiness

### GET `/api/v1/users/me/readiness`

Get an aggregate readiness score for the current user.

**Query parameters:**

| Name           | Type | Required | Description                                          |
|----------------|------|----------|------------------------------------------------------|
| `resume_id`    | UUID | No       | If provided, include CV score and gap in calculation |
| `job_posting_id`| UUID | No      | If provided with resume_id, include gap penalty      |

**Response `payload`:**
```json
{
  "combined_score": 72.5,
  "cv_score": 80,
  "session_avg": 68.3,
  "gap_severity": "medium",
  "trend": "stable"
}
```

- `combined_score`: 0–100, weighted combination of CV + sessions + gap
- `cv_score`, `session_avg`, `gap_severity`: `null` when not applicable
- `trend`: `"improving"` | `"stable"` | `"declining"` (currently always `"stable"`)

**Example:**
```typescript
const params = new URLSearchParams();
if (resumeId) params.set("resume_id", resumeId);
if (jobPostingId) params.set("job_posting_id", jobPostingId);

const res = await fetch(`${API_BASE}/users/me/readiness?${params}`, {
  headers: { Authorization: `Bearer ${accessToken}` },
});
const { success, payload } = await res.json();
```

---

## Suggested UI Flows

1. **CV Score page**
   - File upload → `POST /resumes/score` → show score, breakdown, suggestions
   - Or: if user has a resume → "Score my CV" button → `GET /resumes/{id}/score`

2. **Job match / suitability**
   - After selecting resume + job → `POST /match/skill-gap` → show alerts, missing skills, suggestions

3. **Dashboard / readiness**
   - Call `GET /users/me/readiness?resume_id=...&job_posting_id=...` (if user has selected them) → show combined score, cv_score, session_avg, gap_severity

---

## Backend Config (for reference)

Ensure these are set in backend `.env` for CV scoring to work:

```
CV_SCORING_ENABLED=true
CV_SCORING_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

Skill-gap and readiness endpoints do not require any extra config.
