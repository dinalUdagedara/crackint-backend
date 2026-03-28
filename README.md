# Crackint Backend API

Backend for **Crackint** — a personalized interview prep platform. FastAPI + Python; resume and job description NER extraction (implemented), with chat sessions, AI feedback, skill-gap analysis, and more planned.

## About / Features

**Core (MVP)**  
- **Personalized interview prep** — Upload resume + job poster; parse both for technical, behavioral, and system-design prep.  
- **Chat-style interview sessions** — Interactive text Q&A instead of rigid video.  
- **AI feedback engine** — Semantic analysis of answers; feedback on content, clarity, relevance; per-session scores and overall readiness score.  
- **Session history** — Each prep session saved as a chat thread; revisit and track progress over time.

**Resume & CV**  
- **Resume/CV NER extraction** *(implemented)* — Upload PDF or paste text; extract NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE (BERT-BiLSTM-CRF + hybrid rules).  
- **Job description NER extraction** *(implemented)* — Upload job description PDF or paste text; when **job poster NER** is set (`JOB_POSTER_NER_LOAD_DIR`), extract JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE; otherwise fallback to resume NER (SKILL, OCCUPATION, etc.).  
- **Custom CV parsing** — PDF/image parsing with copy-paste fallback; structured CV profile for downstream features.  
- **CV scoring & dashboard** *(implemented)* — Rate CV strength (0–100) by passing PDF/image directly to LLM vision model; `POST /resumes/score`. Fallback: `GET /resumes/{id}/score` uses stored raw text.  
- **CV–job suitability alerts** *(implemented)* — `POST /match/skill-gap` returns missing skills, weak experience/education, suggestions, and structured alerts.  
- **Combined readiness** *(implemented)* — `GET /users/me/readiness` aggregates CV score, session scores, and gap severity.

**Interview & prep**  
- **Role-specific skill-gap analysis** *(implemented)* — `POST /match/skill-gap` compares resume vs job; returns missing skills, weak areas, suggestions.  
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
   # Edit .env: set RESUME_NER_LOAD_DIR and/or JOB_POSTER_NER_LOAD_DIR to your model directories.
   # For Session Q&A: set OPENAI_API_KEY and SESSION_QA_AGENT_ENABLED=true.
   # For CV scoring: set CV_SCORING_ENABLED=true (uses same OPENAI_API_KEY).
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

## NER model paths

**Resume NER**  
- The model is hosted on **Hugging Face**: [dinalUdagedara/resume-entity-extractor](https://huggingface.co/dinalUdagedara/resume-entity-extractor). To download it locally: run `python scripts/download_resume_ner_model.py` (requires `poetry install --with download` or `pip install huggingface_hub`), then set **`RESUME_NER_LOAD_DIR=./model/resume_ner`** in `.env`.
- **Google Drive:** The model can be stored in a shared Drive folder or as a single zip file. Set **`RESUME_NER_GDRIVE_FOLDER_ID`** or **`RESUME_NER_GDRIVE_FILE_ID`** so the app downloads at startup (`poetry install --with download` or `pip install gdown`), or run `python scripts/download_resume_ner_from_gdrive.py` (optionally with a folder ID or `--file FILE_ID`) then set **`RESUME_NER_LOAD_DIR=./model/resume_ner`**. See **RESUME_NER_SETUP.md** for details.
- Alternatively, set `RESUME_NER_LOAD_DIR` to any directory that already contains the saved model (e.g. from your notebook or a manual Drive download). See **RESUME_NER_SETUP.md** for details.
- If `RESUME_NER_LOAD_DIR` is not set or the path does not exist, the API still runs and returns stub/minimal rule-based extraction.
- Implementation details (hybrid rules, model load, tokenization): see **`app/ml/resume_ner.py`** and **`RESUME_NER_SETUP.md`**.

**Job poster NER**  
- Set **`JOB_POSTER_NER_LOAD_DIR`** to the directory containing your job poster NER model (e.g. `./model/job_poster_ner`). The folder must contain `bert_bilstm_crf_state.pt`, `ner_config.json`, and the tokenizer files (`vocab.txt`, etc.). If not set or the path does not exist, job description extraction falls back to the resume NER pipeline.

## API

See **[API_OVERVIEW.md](API_OVERVIEW.md)** for a full list of endpoints, parameters, and response shapes.

- **GET /api/v1/health** — Health check (`{"status": "ok"}`).
- **GET /api/v1/resumes** — List all resumes (paginated; optional `user_id` filter).
- **GET /api/v1/resumes/{resume_id}** — Get a single resume by ID.
- **POST /api/v1/resumes/extract** — Create resume: upload PDF or paste text, extract entities, persist.
- **PUT /api/v1/resumes/{resume_id}** — Update resume: new PDF or text, re-extract, update record.
- **PATCH /api/v1/resumes/{resume_id}** — Update only selected entity fields (e.g. NAME, SKILL); send JSON `{ "entities": { "NAME": ["..."], "SKILL": [...] } }`.
- **POST /api/v1/resumes/score** — Score a CV from file upload (PDF/image); requires CV_SCORING_ENABLED.
- **GET /api/v1/resumes/{resume_id}/score** — Score an existing resume.
- **POST /api/v1/match/skill-gap** — Compare resume vs job; returns gaps, suggestions, alerts.
- **GET /api/v1/users/me/readiness** — Combined readiness (CV + sessions + gap).
- **DELETE /api/v1/resumes** — Delete all resumes.
- **POST /api/v1/resumes/extract** — Create resume: extract entities from a PDF or text.
  - Either upload a **PDF file** (multipart form field `file`), or
  - Send raw text (form field `text`).
  - Response: `{ "success": true, "message": "...", "payload": { "entities": { "NAME": [...], "EMAIL": [...], "SKILL": [...], ... }, "raw_text": "..." } }`.
- **POST /api/v1/jobs/extract** — Extract entities from a job description.
  - Either upload a **PDF file** (multipart form field `file`), or
  - Send raw text (form field `text`).
  - When job poster NER is used: `entities` include JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE. Otherwise (fallback): SKILL, OCCUPATION, EDUCATION, EXPERIENCE.

## Project layout

- `app/main.py` — FastAPI app factory.
- `app/api/router.py` — Central router; includes health, resume, and job routers.
- `app/api/resume/` — Resume upload + NER extraction (route, service, schemas).
- `app/api/job/` — Job description upload + NER extraction (route, service, schemas).
- `app/api/health/` — Health check stub.
- `app/api/match/` — Skill-gap analysis.
- `app/api/users/` — User readiness, etc.
- `app/ml/resume_ner.py` — Resume NER (load + `parse_resume_hybrid`).
- `app/ml/job_poster_ner.py` — Job poster NER (load + `parse_job_poster_hybrid`); used for job description extraction when `JOB_POSTER_NER_LOAD_DIR` is set.
- `app/services/text_extraction.py` — PDF → text (PyMuPDF).
- `app/services/file_to_vision.py` — PDF → images for vision API.
- `app/services/cv_scoring.py` — CV scoring orchestration.
- `app/services/skill_gap_service.py` — Resume vs job gap analysis.
- `app/services/readiness_aggregator.py` — Combined readiness score.
- `app/agents/cv_scoring_agent.py` — LLM vision/text CV scoring.
- `app/common/` — Shared response model and exceptions.
- `server.py` — Entry point for running the app.
- `scripts/download_resume_ner_model.py` — Download the Resume NER model from Hugging Face to `model/resume_ner`.
