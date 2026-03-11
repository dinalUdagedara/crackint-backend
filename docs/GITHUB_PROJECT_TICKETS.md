# CrackInt Backend – GitHub Project Tickets

**Purpose:** Task breakdown for creating GitHub project tickets. Use this doc to copy-paste ticket titles, descriptions, acceptance criteria, and labels when setting up the project board.

**Context sources:**
- `docs/NEXT_STEPS_KANBAN.md` (crackint-backend)
- `docs/ROADMAP.md` (crackint-backend)
- `model-traning-1:30/docs/project/proposal-summary.md`
- `model-traning-1:30/docs/ipd/requirements-implemented-vs-pending.md`

**Last updated:** Feb 17, 2026

---

## How to Use This Document

1. Create a GitHub Project (Kanban or Table) for the CrackInt backend.
2. Use each ticket section below to create an Issue.
3. Add labels (e.g. `epic`, `backend`, `api`, `ml`, `auth`, `priority:high`).
4. Link tickets to milestones (e.g. "MVP March 2026", "Post-MVP April 2026").
5. Optionally use GitHub Projects' "Notes" for Backlog items before converting to Issues.

---

## EPIC 1: Question Generation MVP (Todo – High Priority)

### Ticket 1.1: Design LLM Prompt for Question Generation

**Title:** `[Backend] Design LLM prompt template for question generation`

**Description:**
Design the prompt template for the question generation service. The prompt must take structured inputs and produce a single interview question suitable for a chat-based prep session.

**Context:**
- FR08: Generate 10–15 personalized, role-specific questions (LLM from resume + job).
- Current Kanban: In Progress – LLM prompt templates.

**Inputs:**
- Role level (INTERN / ASE / SSE)
- Job entities (skills, qualifications, responsibilities)
- Resume entities (skills, experience, education)
- Previous messages in session (to avoid repeats)

**Outputs:**
- Single question text
- Optional difficulty hint (for future adaptive logic)

**Acceptance Criteria:**
- [ ] Prompt template documented (e.g. in `docs/` or code comments)
- [ ] Input/output schema documented
- [ ] Example prompt + sample response included

**Labels:** `epic:question-generation`, `design`, `backend`

---

### Ticket 1.2: Implement Question Generation Service

**Title:** `[Backend] Implement question generation service`

**Description:**
Implement a service that, given `(resume_id, job_posting_id, session_id)`, calls the LLM to generate the next interview question. Support question types: `technical`, `behavioral`, `system_design`.

**Context:**
- Kanban Todo: Question generation (MVP).

**Acceptance Criteria:**
- [ ] Service accepts `resume_id`, `job_posting_id`, `session_id`, optional `question_type`
- [ ] Loads resume entities, job entities, and previous messages from DB
- [ ] Calls LLM with designed prompt
- [ ] Returns structured response: question text + optional metadata
- [ ] Handles LLM errors gracefully (e.g. fallback or clear error response)
- [ ] Unit tests for service (mock LLM)

**Labels:** `epic:question-generation`, `backend`, `api`, `ml`, `priority:high`

---

### Ticket 1.3: Add POST /sessions/{id}/next-question Endpoint

**Title:** `[Backend] Add POST /api/v1/sessions/{id}/next-question endpoint`

**Description:**
Expose the question generation service via a new REST endpoint. The generated question must be stored as a `Message` with `sender=ASSISTANT` and `type=QUESTION`.

**Context:**
- Kanban Todo: Wire to new endpoint.

**Acceptance Criteria:**
- [ ] `POST /api/v1/sessions/{id}/next-question` implemented
- [ ] Request body supports optional `question_type` (technical | behavioral | system_design)
- [ ] On success: generated question stored as `Message`; response includes the question
- [ ] 404 if session not found
- [ ] Integration test covering happy path
- [ ] OpenAPI docs updated

**Labels:** `epic:question-generation`, `backend`, `api`, `priority:high`

**Depends on:** 1.1, 1.2

---

## EPIC 2: Answer Evaluation & Feedback MVP (Todo – High Priority)

### Ticket 2.1: Design LLM Prompt for Answer Evaluation

**Title:** `[Backend] Design LLM prompt template for answer evaluation`

**Description:**
Design the prompt template for semantic evaluation of user answers. The LLM should evaluate content depth, relevance, clarity, and structure.

**Context:**
- FR11: Evaluate responses using semantic analysis (depth, relevance, structure, clarity).
- FR12: Real-time feedback: score 0–100, strengths, areas for improvement, actionable suggestions.
- Current Kanban: In Progress – LLM prompt templates.

**Inputs:**
- Question text
- User answer
- Resume entities, job entities
- Role level

**Outputs:**
- Text feedback (strengths, areas for improvement, suggestions)
- Numeric score (0–100)
- Dimension tags (e.g. `technical`, `communication`)

**Acceptance Criteria:**
- [ ] Prompt template documented
- [ ] Output schema (score, feedback, tags) documented
- [ ] Example prompt + sample response included

**Labels:** `epic:answer-evaluation`, `design`, `backend`

---

### Ticket 2.2: Implement Answer Evaluation Service

**Title:** `[Backend] Implement answer evaluation service`

**Description:**
Implement a service that takes `(question, answer, resume/job context)` and returns structured feedback: text feedback, 0–100 score, dimension tags.

**Context:**
- Kanban Todo: Answer evaluation & feedback (MVP).

**Acceptance Criteria:**
- [ ] Service accepts question, answer, resume entities, job entities, role level
- [ ] Calls LLM with designed prompt
- [ ] Returns: feedback text, score (0–100), dimension tags
- [ ] Handles LLM errors gracefully
- [ ] Unit tests for service (mock LLM)

**Labels:** `epic:answer-evaluation`, `backend`, `api`, `ml`, `priority:high`

---

### Ticket 2.3: Add POST /sessions/{id}/evaluate-answer Endpoint

**Title:** `[Backend] Add POST /api/v1/sessions/{id}/evaluate-answer endpoint`

**Description:**
Expose the answer evaluation service via REST. The feedback must be saved as a `Message` with `sender=ASSISTANT`, `type=FEEDBACK`, and metadata (score, tags).

**Context:**
- Kanban Todo: New endpoint + persist feedback.

**Acceptance Criteria:**
- [ ] `POST /api/v1/sessions/{id}/evaluate-answer` implemented
- [ ] Request body: `answer` text (and optionally question_id or last question inferred)
- [ ] On success: feedback stored as `Message` with metadata (score, dimension tags)
- [ ] Response includes feedback text, score, tags
- [ ] 404 if session not found
- [ ] Integration test covering happy path
- [ ] OpenAPI docs updated

**Labels:** `epic:answer-evaluation`, `backend`, `api`, `priority:high`

**Depends on:** 2.1, 2.2

---

## EPIC 3: Session Summary & Readiness Score (Todo)

### Ticket 3.1: Update Session Summary After Each Evaluated Answer

**Title:** `[Backend] Recompute session summary and readiness_score after each evaluated answer`

**Description:**
After each answer evaluation, recompute the session-level `readiness_score`, `summary.strengths`, and `summary.areas_for_improvement`. Persist on `PrepSession` and return in `GET /api/v1/sessions/{id}` and `GET /api/v1/sessions/{id}/with-messages`.

**Context:**
- Kanban Todo: Update session summary & readiness_score.

**Acceptance Criteria:**
- [ ] `readiness_score` computed (e.g. average of answer scores, or weighted)
- [ ] `summary.strengths` and `summary.areas_for_improvement` updated (LLM-generated or aggregated from feedback)
- [ ] Persisted on `PrepSession` after each evaluation
- [ ] `GET /api/v1/sessions/{id}` and `GET /api/v1/sessions/{id}/with-messages` include readiness_score and summary
- [ ] Unit/integration test for summary update logic

**Labels:** `epic:session-summary`, `backend`, `api`

**Depends on:** 2.2, 2.3

---

## EPIC 4: Session Filtering & Ownership (Todo)

### Ticket 4.1: Add user_id Filter to GET /sessions

**Title:** `[Backend] Add user_id filter to GET /api/v1/sessions`

**Description:**
Add optional `user_id` query parameter to `GET /api/v1/sessions` so sessions can be filtered by owner. Document the convention: frontend should pass `user_id` once auth is added.

**Context:**
- Kanban Todo: Session filtering & ownership.

**Acceptance Criteria:**
- [ ] `GET /api/v1/sessions?user_id={id}` filters by user
- [ ] Without `user_id`, current behavior preserved (or document that it will change when auth is added)
- [ ] Frontend docs updated: `docs/frontend-sessions-and-job-postings.md`
- [ ] Integration test for filtered list

**Labels:** `epic:sessions`, `backend`, `api`, `auth-prep`

---

## EPIC 5: Agent Configuration & Env (In Progress)

### Ticket 5.1: Configure Session QA Agent Env Vars

**Title:** `[Backend] Configure and document Session QA agent env vars`

**Description:**
Decide whether to reuse existing OpenAI config (from entity agents) or add separate env flags for the session Q&A flow. Document all required env vars.

**Context:**
- Current Kanban: In Progress – Agent configuration.

**Acceptance Criteria:**
- [ ] Env vars defined (e.g. `SESSION_QA_AGENT_ENABLED`, model name, temperature)
- [ ] Documented in README or `.env.example`
- [ ] Config loaded in `app/config.py` (or equivalent)
- [ ] Service uses config for question generation and answer evaluation

**Labels:** `backend`, `config`, `priority:medium`

---

## EPIC 6: Backlog – Later Phases

### Ticket 6.1: LLM Question Generation v2 (Role + Difficulty Curve)

**Title:** `[Backend] LLM question generation v2 – role-based + difficulty curve`

**Description:**
Enhance question generation to use role level (INTERN/ASE/SSE), job entities, and resume entities. Maintain a difficulty curve across the session.

**Context:**
- Kanban Backlog: LLM-powered question generation v2.

**Acceptance Criteria:**
- [ ] Questions adapt to role level
- [ ] Difficulty progression across session (easy → medium → hard)
- [ ] Uses full job + resume entity context

**Labels:** `epic:question-generation`, `backend`, `ml`, `backlog`

---

### Ticket 6.2: Gap Analysis Service

**Title:** `[Backend] Gap analysis service – resume vs job entities`

**Description:**
Implement a service that compares resume entities with job entities (skills, experience, education) and returns structured gaps and suggestions for improvement.

**Context:**
- Kanban Backlog: Gap analysis service.
- ROADMAP Step 5: CV vs job poster gap analysis.

**Acceptance Criteria:**
- [ ] Service accepts resume_id, job_posting_id
- [ ] Returns: missing skills, weak experience/education, suggested improvements
- [ ] Endpoint: `POST /api/v1/match/skill-gap` (or similar)

**Labels:** `epic:gap-analysis`, `backend`, `api`, `backlog`

---

### Ticket 6.3: Readiness Dashboard APIs

**Title:** `[Backend] Readiness dashboard APIs – aggregate scores and trends`

**Description:**
Expose APIs for aggregated readiness across multiple sessions: trends over time, top N weaknesses per user.

**Context:**
- Kanban Backlog: Readiness dashboard APIs.
- FR15–FR16: Progress analytics, charts.

**Acceptance Criteria:**
- [ ] Endpoint(s) to aggregate scores across sessions
- [ ] Support for trends (e.g. last N sessions)
- [ ] Top N weaknesses / areas for improvement per user

**Labels:** `epic:dashboard`, `backend`, `api`, `backlog`

---

### Ticket 6.4: Gamification – Streaks, Badges, Leaderboard

**Title:** `[Backend] Gamification – streaks, badges, leaderboard endpoints`

**Description:**
Add gamification features: streaks, badges, point rules, and basic leaderboard endpoints.

**Context:**
- Kanban Backlog: Gamification.

**Acceptance Criteria:**
- [ ] Streak logic (e.g. consecutive days with practice)
- [ ] Badge rules (e.g. first session, 10 sessions, perfect score)
- [ ] Leaderboard endpoint(s)

**Labels:** `epic:gamification`, `backend`, `api`, `backlog`

---

## EPIC 7: Auth & Security (Backlog – Foundational)

### Ticket 7.1: User Registration and Auth (FR01–FR02)

**Title:** `[Backend] User registration and secure auth`

**Description:**
Implement user registration with email/password, secure auth (bcrypt, JWT), and session management.

**Context:**
- FR01: Register with email, password, basic profile.
- FR02: Secure auth, encrypted password storage.
- NFR01: bcrypt, AES-256 at rest; NFR16: JWT over HTTPS.

**Acceptance Criteria:**
- [ ] `POST /api/v1/auth/register`
- [ ] `POST /api/v1/auth/login`
- [ ] Passwords hashed with bcrypt (≥10 rounds)
- [ ] JWT issued on login; validated on protected routes
- [ ] Basic user profile stored

**Labels:** `epic:auth`, `backend`, `api`, `security`, `backlog`

---

### Ticket 7.2: Protect Endpoints with Auth Middleware

**Title:** `[Backend] Protect API endpoints with auth middleware`

**Description:**
Add auth middleware so that resumes, job postings, sessions, and messages require authenticated user. Enforce `user_id` ownership.

**Context:**
- Post-auth: all user-specific resources must be tied to logged-in user.

**Acceptance Criteria:**
- [ ] Auth middleware validates JWT
- [ ] Resumes, sessions, job postings filtered by authenticated user
- [ ] 401 for unauthenticated requests to protected endpoints

**Labels:** `epic:auth`, `backend`, `api`, `security`, `backlog`

**Depends on:** 7.1

---

## Reference: Done (No New Tickets – Baseline)

The following are **already implemented**. Use as context when creating tickets; no new tickets needed.

| Area | What's Done |
|------|-------------|
| Entity extraction | `POST /api/v1/resumes/extract` with DB persistence; `POST /api/v1/jobs/extract` with AI validation |
| Job postings | `POST`, `GET` (list + pagination), `GET /{id}` |
| Prep sessions | `POST`, `GET` (list), `GET /{id}`, `GET /{id}/with-messages` |
| Messages | `POST /api/v1/sessions/{id}/messages`, `GET /api/v1/sessions/{id}/messages` |
| Frontend docs | `docs/frontend-sessions-and-job-postings.md` |

---

## Suggested GitHub Project Structure

| Column | Tickets |
|--------|---------|
| **Backlog** | 6.1, 6.2, 6.3, 6.4, 7.1, 7.2 |
| **Todo** | 1.1–1.3, 2.1–2.3, 3.1, 4.1, 5.1 |
| **In Progress** | 1.1, 2.1, 5.1 (design/config) |
| **Done** | (Reference: Done section above) |

**Recommended order to tackle Todo:**
1. 5.1 (Agent config) – unblocks LLM services
2. 1.1, 2.1 (Design prompts) – parallel
3. 1.2, 1.3 (Question gen) – then 2.2, 2.3 (Answer eval)
4. 3.1 (Session summary)
5. 4.1 (user_id filter)

---

*Use this document as the single source for creating and describing GitHub project tickets for the CrackInt backend.*
