## Crackint Backend – Next Steps Kanban

Last updated: Feb 11, 2026  
Scope: Backend work after sessions + job postings MVP

---

## 🧠 Backlog (Later Phases)

- **LLM-powered question generation v2**
  - Use role (INTERN/ASE/SSE) + job entities + resume entities.
  - Maintain difficulty curve across the session.
- **Gap analysis service**
  - Compare resume vs job entities (skills, experience, education).
  - Return structured gaps + suggestions.
- **Readiness dashboard APIs**
  - Aggregate scores across multiple sessions.
  - Expose trends and top N weaknesses per user.
- **Gamification**
  - Streaks, badges, point rules.
  - Basic leaderboard endpoints.

---

## 🟡 Todo (Next Focus)

- **Question generation (MVP)**
  - Service that, given `(resume_id, job_posting_id, session_id)`, asks LLM for the **next question**.
  - Include parameters for type: `technical | behavioral | system_design`.
  - Wire to new endpoint: `POST /api/v1/sessions/{id}/next-question`.
  - Store generated question as `Message` with `sender=ASSISTANT`, `type=QUESTION`.

- **Answer evaluation & feedback (MVP)**
  - Service that takes `(question, answer, resume/job context)` and returns:
    - Text feedback.
    - 0–100 score.
    - Dimension tags (e.g., `technical`, `communication`).
  - New endpoint: `POST /api/v1/sessions/{id}/evaluate-answer`.
  - Save feedback as `Message` with `sender=ASSISTANT`, `type=FEEDBACK`, `metadata.score`, etc.

- **Update session summary & readiness_score**
  - After each evaluated answer, recompute session-level:
    - `readiness_score` (average of answer scores, or weighted).
    - `summary.strengths` and `summary.areas_for_improvement` (LLM-generated).
  - Persist on `PrepSession` and return in:
    - `GET /api/v1/sessions/{id}`
    - `GET /api/v1/sessions/{id}/with-messages`

- **Session filtering & ownership**
  - Add `user_id` filter to `GET /api/v1/sessions` (similar to resumes/job_postings).
  - Document convention: frontend must always pass `user_id` once auth is added.

---

## 🟢 In Progress / Design

- **LLM prompt templates**
  - Design prompt for **question generation**:
    - Inputs: role level, job entities, resume entities, previous messages.
    - Output: single question + difficulty hint.
  - Design prompt for **answer evaluation**:
    - Inputs: question, answer, entities, role level.
    - Output: score + textual feedback + improvement tips.

- **Agent configuration**
  - Decide whether to reuse existing OpenAI config (from entity agents) or add:
    - Separate env flags: `SESSION_QA_AGENT_ENABLED`, model name, temperature, etc.
  - Document required env vars.

---

## ✅ Done (Current State)

- **Entity extraction**
  - `/api/v1/resumes/extract` with DB persistence.
  - `/api/v1/jobs/extract` with AI validation (no DB write).

- **Job postings**
  - `POST /api/v1/job-postings` – create from `/jobs/extract` output.
  - `GET /api/v1/job-postings` – list with pagination.
  - `GET /api/v1/job-postings/{id}` – detail.

- **Prep sessions**
  - `POST /api/v1/sessions` – create (linking user/resume/job).
  - `GET /api/v1/sessions` – list.
  - `GET /api/v1/sessions/{id}` – detail (no messages).
  - `GET /api/v1/sessions/{id}/with-messages` – detail + messages.

- **Messages**
  - `POST /api/v1/sessions/{id}/messages` – append chat message.
  - `GET /api/v1/sessions/{id}/messages` – list messages (chronological).

- **Frontend docs**
  - `docs/frontend-sessions-and-job-postings.md` – integration guide for current APIs.

---

## 🔁 How to use this Kanban

- **Backend**:
  - Pull items from **Todo** into **In Progress**, starting with:
    - Question generation (MVP)
    - Answer evaluation & feedback (MVP)
  - Move them to **Done** once implemented and documented.
- **Frontend**:
  - Build against items in **Done**.
  - Prepare UI placeholders for upcoming endpoints in **Todo** (e.g., “Get next question”, “Evaluate answer”) so wiring later is easy.

