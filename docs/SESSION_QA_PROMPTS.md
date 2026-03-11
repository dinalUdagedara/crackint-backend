# Session Q&A LLM Prompt Templates

Design doc for the Session Q&A agent: **question generation** and **answer evaluation**. Used by `POST /api/v1/sessions/{id}/next-question` and `POST /api/v1/sessions/{id}/evaluate-answer`.

**Last updated:** Feb 2026

---

## 1. Question Generation

### 1.1 Purpose

Generate the **next interview question** for a chat-style prep session. The question should be personalized to the candidate’s resume and the target job, and avoid repeating questions already asked in the session.

### 1.2 Inputs

| Input | Type | Description |
|-------|------|--------------|
| `role_level` | `str` | Candidate level: `INTERN`, `ASE`, `SSE`, or `OTHER`. Adjust difficulty and expectations. |
| `job_entities` | `Dict[str, List[str]]` | From job posting NER: e.g. `JOB_TITLE`, `COMPANY`, `SKILLS_REQUIRED`, `EXPERIENCE_REQUIRED`, `EDUCATION_REQUIRED`, `JOB_TYPE`, etc. |
| `resume_entities` | `Dict[str, List[str]]` | From resume NER: e.g. `NAME`, `SKILL`, `OCCUPATION`, `EDUCATION`, `EXPERIENCE`, etc. |
| `previous_messages` | `List[{sender, type, content}]` | Messages in this session so far (chronological). Used to avoid repeating questions. |
| `question_type` | `str` (optional) | Requested type: `technical`, `behavioral`, or `system_design`. If omitted, model may choose. |

### 1.3 Output Schema

The LLM must return **valid JSON** with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | `str` | Yes | The interview question text (one question only). |
| `difficulty` | `str` | No | Hint for future adaptive logic: e.g. `easy`, `medium`, `hard`. |
| `question_type` | `str` | No | One of: `technical`, `behavioral`, `system_design`. |

**Example:**

```json
{
  "question": "Describe a time when you had to debug a production issue under time pressure. What was your approach and outcome?",
  "difficulty": "medium",
  "question_type": "behavioral"
}
```

### 1.4 Prompt Template

**System prompt:**

```
You are an expert technical interviewer. Your task is to generate exactly one interview question for a practice session.

Context you will receive:
- Role level: INTERN, ASE, or SSE (adjust question depth and scope accordingly).
- Job posting entities: job title, company, required skills, experience, education, job type.
- Candidate resume entities: skills, occupation, education, experience.
- The list of questions and messages already exchanged in this session (do not repeat or rephrase those questions).

Rules:
- Output exactly one new question suitable for the given role level and aligned with the job requirements and the candidate's background.
- Prefer questions that let the candidate demonstrate relevant skills or experience from their resume where applicable.
- If question_type is specified (technical, behavioral, or system_design), generate that type; otherwise you may choose.
- Respond with a single JSON object with keys: "question" (string), optional "difficulty" (easy|medium|hard), optional "question_type" (technical|behavioral|system_design).
- Do not include any text outside the JSON object.
```

**User prompt (fill-in):**

```
Role level: {role_level}

Job posting entities (key: list of values):
{job_entities_json}

Candidate resume entities (key: list of values):
{resume_entities_json}

Previous messages in this session (do not repeat these as questions):
{previous_messages_formatted}

Requested question type (or leave empty to choose): {question_type}
```

### 1.5 Example

**Inputs:**

- `role_level`: `ASE`
- `job_entities`: `{"JOB_TITLE": ["Software Engineer"], "SKILLS_REQUIRED": ["Python", "AWS", "SQL"], "EXPERIENCE_REQUIRED": ["2+ years"]}`
- `resume_entities`: `{"SKILL": ["Python", "Java"], "OCCUPATION": ["Software Developer"], "EXPERIENCE": ["1 year internship"]}`
- `previous_messages`: one QUESTION: "Tell me about yourself."
- `question_type`: `technical`

**Sample LLM response:**

```json
{
  "question": "The job mentions AWS and SQL. Can you walk us through a project where you used a relational database and how you would approach moving part of that workload to AWS?",
  "difficulty": "medium",
  "question_type": "technical"
}
```

---

## 2. Classify user message (redirect / next question / substantive)

Before running full answer evaluation, the backend calls the LLM to classify the user message. All messages go through the LLM (no heuristic fast path).

**Outcomes:**
1. **SUBSTANTIVE_ANSWER** — User is answering the question (even if short or unsure). Caller runs full evaluation and then generates the next question.
2. **NEXT_QUESTION** — User explicitly asks to skip (e.g. "next question", "move on", "skip", "let's move on"). Caller skips evaluation and immediately generates the next question (no redirect, no feedback).
3. **Redirect** — Greeting, off-topic, "I don't know", "hint?", small talk. The LLM returns one short, warm sentence that gently brings the user back. Stored as FEEDBACK with `meta.redirect = "true"`; excluded from session summary and readiness.

- **Function:** `classify_and_redirect(question, user_message)` returns `None` (substantive), `NEXT_QUESTION_SENTINEL`, or a redirect string.
- **Prompt:** `REDIRECT_SYSTEM_PROMPT`; user content is last question + user message. Model replies with exactly one of: `SUBSTANTIVE_ANSWER`, `NEXT_QUESTION`, or one short redirect sentence. `DEFAULT_REDIRECT_MESSAGE` used as fallback when LLM fails.

---

## 3. Answer Evaluation

### 3.1 Purpose

Evaluate the candidate’s **answer** to an interview question and return structured feedback: text feedback, a numeric score (0–100), and dimension tags for analytics.

### 4.2 Inputs

| Input | Type | Description |
|-------|------|--------------|
| `question` | `str` | The interview question that was asked. |
| `answer` | `str` | The candidate’s answer text. |
| `role_level` | `str` | `INTERN`, `ASE`, `SSE`, or `OTHER`. Expectations scale with level. |
| `job_entities` | `Dict[str, List[str]]` | Job posting entities (for relevance to role). |
| `resume_entities` | `Dict[str, List[str]]` | Resume entities (for relevance to candidate background). |

### 3.3 Output Schema

The LLM must return **valid JSON** with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `feedback` | `str` | Yes | Text feedback: strengths, areas for improvement, and actionable suggestions. |
| `score` | `int` | Yes | Numeric score 0–100 (inclusive). |
| `dimension_tags` | `List[str]` | No | Tags such as `technical`, `communication`, `structure`, `relevance`, `clarity`. |

**Example:**

```json
{
  "feedback": "Strong use of a concrete example (STAR). You could improve by quantifying the impact (e.g., latency or error rate) and mentioning what you would do differently now.",
  "score": 72,
  "dimension_tags": ["behavioral", "communication", "structure"]
}
```

### 3.4 Prompt Template

**System prompt:**

```
You are an expert technical interviewer evaluating a candidate's answer in a practice session.

Your task: Given the question and the candidate's answer, produce:
1. Text feedback: 2–4 sentences covering strengths, areas for improvement, and one or two actionable suggestions.
2. A score from 0 to 100 (inclusive). Consider: depth of content, relevance to the question, clarity, structure (e.g. STAR for behavioral), and fit for the role level.
3. A short list of dimension tags (e.g. technical, communication, structure, relevance, clarity, behavioral) that best describe what your feedback addresses.

Role level (INTERN / ASE / SSE) is provided; calibrate expectations accordingly (e.g. INTERN: more lenient on depth; SSE: expect more leadership/system thinking).

Respond with a single JSON object with keys: "feedback" (string), "score" (integer 0–100), "dimension_tags" (array of strings). Do not include any text outside the JSON object.
```

**User prompt (fill-in):**

```
Role level: {role_level}

Question:
{question}

Candidate's answer:
{answer}

Job context (for relevance):
{job_entities_json}

Candidate background (for relevance):
{resume_entities_json}
```

### 3.5 Example

**Inputs:**

- `question`: "Describe a time when you had to debug a production issue under time pressure."
- `answer`: "In my internship we had a bug in the payment API. I looked at the logs, found it was a null pointer in one microservice, and fixed it. We deployed a patch within an hour."
- `role_level`: `INTERN`
- `job_entities`: `{"JOB_TITLE": ["Software Engineer"], "SKILLS_REQUIRED": ["troubleshooting", "Python"]}`
- `resume_entities`: `{"SKILL": ["Python"], "EXPERIENCE": ["6-month internship"]}`

**Sample LLM response:**

```json
{
  "feedback": "Good that you gave a concrete example and mentioned logs and a quick turnaround. To strengthen the answer: (1) briefly describe the impact (e.g. users affected, revenue at risk), (2) mention how you prioritized or communicated with the team, and (3) one thing you’d do differently next time. This will show ownership and reflection.",
  "score": 68,
  "dimension_tags": ["behavioral", "technical", "structure", "clarity"]
}
```

---

## 4. Session Summary (strengths / areas_for_improvement)

### 4.1 Purpose

After each answer evaluation, the backend can call the LLM to synthesize all FEEDBACK messages in the session into a short session-level summary: **strengths** and **areas_for_improvement**. This summary is stored on `PrepSession.summary` and returned in `GET /api/v1/sessions/{id}` and `GET /api/v1/sessions/{id}/with-messages`.

### 4.2 Inputs

| Input | Type | Description |
|-------|------|--------------|
| `role_level` | `str` | Candidate level (INTERN, ASE, SSE, OTHER) for context. |
| `feedback_items` | `List[Dict]` | List of `{"content": str, "meta": dict}` — the text and metadata (e.g. dimension_tags) of each FEEDBACK message. Truncated to last N (e.g. 10) to fit context. |
| `job_entities` | `Dict` (optional) | Job posting entities for context. |
| `resume_entities` | `Dict` (optional) | Resume entities for context. |

### 4.3 Output Schema

The LLM must return **valid JSON** with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `strengths` | `str` | Yes | Session-level strengths summary (2–4 bullets or short paragraph). |
| `areas_for_improvement` | `str` | Yes | Session-level areas for improvement summary. |

**Example:**

```json
{
  "strengths": "Clear use of concrete examples; good technical depth on debugging. Structure improved over the session.",
  "areas_for_improvement": "Add metrics and impact (e.g. latency, error rate). Use STAR more consistently for behavioral answers. Mention what you would do differently."
}
```

### 4.4 Prompt Template

**System prompt:** See `SUMMARY_SYSTEM_PROMPT` in `app/agents/session_qa_agent.py` — instructs the model to synthesize feedback into strengths and areas_for_improvement, output JSON only.

**User prompt:** Role level, recent feedback (text + tags), optional job/resume context.

### 4.5 When It Runs

- Called from `post_evaluate_answer` after storing the new FEEDBACK message.
- If the LLM call fails, `readiness_score` is still updated (average of scores); `summary` is left unchanged or set to empty.

---

## 5. Implementation Notes

- **Parsing:** Services must parse LLM output as JSON. Handle malformed output (e.g. fallback score, generic feedback) and log errors.
- **Token limits:** For long `previous_messages`, truncate or summarize (e.g. last N messages or last N questions only) to stay within model context. Session summary uses last N feedback items (`SUMMARY_MAX_FEEDBACK_ITEMS`).
- **Config:** Model and temperature are taken from `app.config.settings`: `SESSION_QA_AGENT_MODEL`, `SESSION_QA_AGENT_TEMPERATURE`. Only call the LLM when `SESSION_QA_AGENT_ENABLED` is true and `OPENAI_API_KEY` is set.
