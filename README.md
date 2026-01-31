# Crackint Backend API

Backend for **Crackint** — a personalized interview prep platform. FastAPI + Python; resume NER extraction (implemented), with chat sessions, AI feedback, skill-gap analysis, and more planned.

## About / Features

**Core (MVP)**  
- **Personalized interview prep** — Upload resume + job poster; parse both for technical, behavioral, and system-design prep.  
- **Chat-style interview sessions** — Interactive Q&A (ChatGPT-style) instead of rigid video.  
- **AI feedback engine** — Semantic analysis of answers; feedback on content, clarity, relevance; per-session scores and overall readiness score.  
- **Session history** — Each prep session saved as a chat thread; revisit and track progress over time.

**Resume & CV**  
- **Resume/CV NER extraction** *(implemented)* — Upload PDF or paste text; extract NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE (BERT-BiLSTM-CRF + hybrid rules).  
- **Custom CV parsing** — PDF/image parsing with copy-paste fallback; structured CV profile for downstream features.  
- **CV scoring & dashboard** — Rate CV strength; overall readiness combining CV strength, session performance, and skill gaps.  
- **CV–job suitability alerts** — Warn when job poster demands skills missing from CV; suggest updates or learning.

**Interview & prep**  
- **Role-specific skill-gap analysis** — Compare CV vs job description; highlight missing competencies.  
- **Adaptive question difficulty** — Difficulty scales with performance inside a session.  
- **Role-based difficulty** — Tailor by level (e.g. Intern, ASE, SSE).  
- **Deadline-aware preparation** — Auto-detect or manual interview dates; prep schedule and reminders.  
- **Practice modes** — Quick practice (short drills) and custom-question mode.

**Other**  
- **Cover letter generation** — One-click draft from CV + job context.  
- **Gamification** — Streaks, badges, points, progress levels; optional leaderboard.  
- **Job suitability by location** — Parse job location (city, country, remote/on-site); compare with user; rate suitability and remote match.

## Run locally

1. Install dependencies (use either **Poetry** or **pip**):

   **Option A — Poetry (recommended if you use it):**

   ```bash
   poetry install
   # then run with: poetry run python server.py  or  poetry run fastapi dev main.py
   ```

   **Option B — pip:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy env template and set options (optional):

   ```bash
   cp .env.example .env
   # Edit .env: set RESUME_NER_LOAD_DIR to your saved NER model directory if you have one
   ```

3. Start the server:

   ```bash
   python server.py
   ```

   Or with uvicorn directly:

   ```bash
   uvicorn app.main:get_app --reload --factory --host 0.0.0.0 --port 8000
   ```

4. Open docs: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)

## NER model path

- Set **`RESUME_NER_LOAD_DIR`** in `.env` to the directory where your saved BERT-BiLSTM-CRF model, tokenizer, and config live (from your notebook’s save step).
- Refactor the notebook’s `load_model()` and `parse_resume_hybrid()` into `app/ml/resume_ner.py` and wire them to this path.
- If `RESUME_NER_LOAD_DIR` is not set or the path does not exist, the API still runs and returns stub/minimal rule-based extraction.

## API

- **GET /api/v1/health** — Health check (`{"status": "ok"}`).
- **POST /api/v1/resumes/extract** — Extract entities from a resume.
  - Either upload a **PDF file** (multipart form field `file`), or
  - Send raw text (form field `text`).
  - Response: `{ "success": true, "message": "...", "payload": { "entities": { "NAME": [...], "EMAIL": [...], "SKILL": [...], ... }, "raw_text": "..." } }`.

## Project layout

- `app/main.py` — FastAPI app factory.
- `app/api/router.py` — Central router; includes health and resume routers.
- `app/api/resume/` — Resume upload + NER extraction (route, service, schemas).
- `app/api/health/` — Health check stub.
- `app/ml/resume_ner.py` — NER integration (refactor notebook load + `parse_resume_hybrid` here).
- `app/services/text_extraction.py` — PDF → text (PyMuPDF).
- `app/common/` — Shared response model and exceptions.
- `server.py` — Entry point for running the app.
