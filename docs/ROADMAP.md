## Crackint Backend Roadmap

Last updated: Feb 11, 2026

---

## 1. Where we are now

- **Core foundations**
  - FastAPI backend running and structured by feature modules.
  - Environment/config management via `app/config.py` and `.env`.

- **Implemented features**
  - **Job entity extraction**
    - Endpoint: `POST /api/v1/jobs/extract`
    - Inputs: `file` (PDF/image) **or** `text`.
    - Output: structured entities (e.g. `JOB_TITLE`, `COMPANY`, `LOCATION`, `SKILLS_REQUIRED`, etc.).
    - Optional AI validation with `validate=true` using:
      - Job poster NER model (`app/ml/job_poster_ner.py`).
      - LLM agent (`app/agents/job_entity_agent.py`) via `validate_and_correct_entities`.
  - **Resume entity extraction**
    - Documented endpoint: `POST /api/v1/resume/extract` (implementation in resume module).
    - Similar `validate=true` support for AI validation.

- **What this enables today**
  - Parse job posters and resumes into structured entities.
  - Run AI validation to improve extraction quality.
  - Use these entities later for:
    - CV–job gap analysis.
    - Scoring and readiness metrics.
    - Personalized interview question generation.

---

## 2. Target features (from product vision)

- **Core MVP**
  - Personalized interview prep from **resume + job poster** (technical, behavioral, system design).
  - Chat-style interview sessions (ChatGPT-like).
  - AI feedback engine with scoring and **readiness score per session**.
  - Session history stored as chat threads.

- **Planned extensions**
  - Role-specific **CV vs job poster skill gap analysis**.
  - Custom CV parsing model and structured profile.
  - CV scoring + dashboard combining:
    - CV strength
    - Chat session performance
    - Skill gaps
  - Suitability alerts (skills, location, role level, deadlines).
  - Adaptive difficulty + role-based difficulty.
  - Deadline-aware prep schedule.
  - Cover letter generation.
  - Gamification (streaks, badges, leaderboard).
  - Practice modes (quick drills, custom questions).

---

## 3. Next steps (step by step)

### Step 1 – Stabilize and finalize parsing layer

- **1.1** Verify job extraction:
  - Write integration tests for `POST /api/v1/jobs/extract` (file + text + `validate=true/false`).
  - Confirm error handling for invalid/large files and missing text/file.
- **1.2** Verify resume extraction:
  - Confirm `POST /api/v1/resume/extract` behavior matches docs.
  - Add similar tests and documentation examples.
- **1.3** Standardize entity schemas:
  - Finalize common schema for job entities and resume entities (names, types, optional/required).
  - Document them clearly for frontend usage.

### Step 2 – Data models for users, resumes, jobs, and sessions

- **2.1** Design persistence models (DB)
  - `User` (basic profile, location, role level).
  - `Resume` (file info + extracted entities + parsed profile snapshot).
  - `JobPosting` (file/text + extracted entities).
  - `PrepSession` (one interview-prep session linked to `User`, `Resume`, `JobPosting`).
  - `Message` (chat-style Q&A messages within a `PrepSession`).
- **2.2** Implement DB layer
  - Create SQLAlchemy models (or your chosen ORM) for the above entities.
  - Add migrations if using Alembic.
- **2.3** Basic CRUD APIs
  - Endpoints to create/list:
    - Resumes and their parsed entities.
    - Job postings and their parsed entities.
    - Prep sessions and their messages (for history).

### Step 3 – MVP chat-style interview sessions

- **3.1** Session lifecycle APIs
  - `POST /api/v1/sessions` – start a new prep session for `(user, resume, job)`.
  - `POST /api/v1/sessions/{id}/messages` – user sends an answer or requests a question.
  - `GET /api/v1/sessions/{id}` – get session with all messages (chat history).
- **3.2** Question generation
  - Service that, given `(resume_entities, job_entities, session_state)`, asks LLM:
    - Technical questions
    - Behavioral questions
    - (Optionally) system design questions
  - Start with simple prompt templates; iterate later.
- **3.3** Session history
  - Persist all `Message` records.
  - Expose API to list previous sessions for a user.

### Step 4 – AI feedback engine and readiness score

- **4.1** Answer evaluation
  - LLM-based service that:
    - Takes the question, user answer, and job/resume context.
    - Returns feedback on: content depth, clarity, relevance.
    - Produces a numeric score per answer (e.g. 0–100).
- **4.2** Aggregate session scoring
  - Compute per-session metrics:
    - Average score across answers.
    - Per-dimension scores (technical, behavioral, communication).
  - Store `PrepSession` summary fields:
    - `readiness_score`
    - `strengths`
    - `areas_for_improvement`
- **4.3** Expose feedback APIs
  - Include feedback and scores in:
    - `GET /api/v1/sessions/{id}` response.
    - Optional `GET /api/v1/sessions/{id}/summary`.

### Step 5 – CV vs job poster gap analysis

- **5.1** Gap analysis service
  - Given `resume_entities` + `job_entities`, compute:
    - Missing skills.
    - Weak experience/education vs job requirements.
    - Suggested improvements (e.g., projects, keywords).
- **5.2** API endpoints
  - `POST /api/v1/match/skill-gap` – returns structured gaps and recommendations.
  - Integrate with session creation so each session has a precomputed gap snapshot.

### Step 6 – Scoring & dashboard layer

- **6.1** CV score
  - LLM or rule-based score for CV strength (0–100) based on parsed resume profile.
- **6.2** Combined readiness score
  - Compute overall readiness from:
    - CV score
    - Recent session readiness scores
    - Gap severity
- **6.3** Dashboard APIs
  - `GET /api/v1/users/{id}/readiness` – returns:
    - Current readiness score.
    - Trend over time (last N sessions).
    - Key gaps to work on.

### Step 7 – Extended features (later phases)

- **7.1** Suitability and alerts
  - Location-based suitability (job vs user).
  - Role-based difficulty (Intern / ASE / SSE).
  - Deadline-aware prep schedule generation.
- **7.2** Content generation extras
  - Cover letter generator for a `(resume, job)` pair.
- **7.3** Gamification
  - Streaks, badges, points, simple leaderboard APIs.
- **7.4** Practice modes
  - Quick practice mode without a specific job.
  - Custom-question mode where user supplies their own questions.

---

## 4. What to implement next (immediate focus)

**Short-term next steps:**

1. Finalize and test **job/resume extraction** (Step 1).
2. Introduce **DB models and basic persistence** for users, resumes, jobs, sessions, and messages (Step 2).
3. Build **MVP chat session APIs** and simple LLM-driven question generation (Step 3).

Once these are done, we will have:

- End-to-end flow: upload resume + job → create session → chat Q&A → store history.
- A solid base to layer on feedback scoring, readiness scores, and dashboards.

