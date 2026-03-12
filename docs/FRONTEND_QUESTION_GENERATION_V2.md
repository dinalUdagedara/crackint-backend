# Question Generation v2 – Frontend Guide

**Purpose:** Context for the frontend (or paste into Cursor when working on the interview-prep UI). Describes the new **Question Generation v2** behaviour and the session endpoints that use it.

**Base URL:** `/api/v1` (e.g. `http://localhost:8000/api/v1`). All session endpoints require **auth** (Bearer JWT).

---

## 1. What’s new (v2)

The backend now uses **Question Generation v2** for all “next question” flows:

1. **Role level is generic seniority (any job type)**  
   `INTERN`, `ASE`, and `SSE` are **not** software-only. They mean:
   - **INTERN** – Entry-level (learning, foundational; any industry).
   - **ASE** – Mid-level (ownership, concrete impact; any industry).
   - **SSE** – Senior (leadership, mentoring, strategy; any industry).

   The **domain** (e.g. technical, behavioral, finance, marketing) comes from the **job posting and resume**. The frontend only sends `role_level`; the backend and LLM use it to adjust question **depth and expectations**, not the industry.

2. **Difficulty curve across the session**  
   Questions in a session now **progress from easier to harder**:
   - First 1–2 questions: **easy**
   - Next 2–3: **medium**
   - After that: **medium/hard**

   The backend suggests this to the LLM automatically. You can **override** it from the frontend by sending `prefer_difficulty: "easy" | "medium" | "hard"` in the request body (see §3). The **response** may include `difficulty` in the generated-question message so the UI can show it.

---

## 2. Endpoints that use v2

These endpoints all use the same v2 logic (role-based depth + difficulty curve). There are **no new endpoints**; only behaviour and response content are enhanced.

| Method | Path | When it generates a question |
|--------|------|-----------------------------|
| POST   | `/sessions/{session_id}/next-question` | Direct “give me the next question” |
| POST   | `/sessions/{session_id}/chat`         | Unified chat: user message → maybe feedback + next question |
| POST   | `/sessions/{session_id}/send`         | Same as chat but different route name |
| POST   | `/sessions/{session_id}/evaluate-answer` | After evaluating answer, or when user says “skip” → next question |

---

## 3. Request / response reference

### 3.1 POST `/sessions/{session_id}/next-question`

**When to use:** User explicitly asks for the next question (e.g. “Next question” button, or first question when starting the interview).

**Request (JSON body, optional):**

```ts
// All fields optional
{
  question_type?: "technical" | "behavioral" | "system_design";  // hint for type of question
  role_level?: "INTERN" | "ASE" | "SSE" | "OTHER";              // default: "ASE"
  prefer_difficulty?: "easy" | "medium" | "hard";              // override: request this difficulty; if omitted, backend uses session curve
}
```

**Response (success):** Standard wrapper `{ success, message, payload }` with:

```ts
payload: {
  question: string;           // The generated interview question text
  difficulty?: string;        // "easy" | "medium" | "hard" (from v2 curve)
  question_type?: string;     // "technical" | "behavioral" | "system_design"
  message_id: string;         // UUID of the stored ASSISTANT QUESTION message
}
```

**Errors:** `404` session not found or not owned; `503` if Session Q&A agent is disabled or LLM unavailable.

---

### 3.2 POST `/sessions/{session_id}/chat` (unified; preferred for main UI)

**When to use:** Each user message in the interview practice flow (answer, greeting, “next question”, etc.). One request per turn.

**Request (JSON body):**

```ts
{
  content: string;   // User’s message (answer, “next question”, “hi”, etc.)
}
```

**Response (success):** `payload.new_messages` is an array of **new** messages for this turn. Typically:

- One **USER** message (type `ANSWER`) with the user’s `content`.
- Then either:
  - **ASSISTANT** `FEEDBACK` (e.g. score, feedback text, or a short redirect), and optionally **ASSISTANT** `QUESTION` (next question), or
  - Only **ASSISTANT** `QUESTION` (e.g. when user said “next question” and we skip evaluation).

Each message shape:

```ts
{
  id: string;           // UUID
  session_id: string;
  sender: "USER" | "ASSISTANT";
  type: "QUESTION" | "ANSWER" | "FEEDBACK";
  content: string;
  meta: Record<string, string | undefined>;  // e.g. { difficulty, question_type, score, dimension_tags }
  created_at: string;   // ISO datetime
  updated_at: string;
}
```

For **QUESTION** messages, `meta` may include:

- `difficulty`: `"easy"` | `"medium"` | `"hard"` (v2 curve).
- `question_type`: `"technical"` | `"behavioral"` | `"system_design"`.

For **FEEDBACK** messages, `meta` may include:

- `score`: string (e.g. `"78"`).
- `dimension_tags`: comma-separated (e.g. `"behavioral,structure"`).
- `redirect`: `"true"` when it’s a short redirect (e.g. greeting) rather than full evaluation.

**Errors:** `404` session not found; `503` if agent disabled.

---

### 3.3 POST `/sessions/{session_id}/send`

Same contract as **chat**: request body `{ content: string, prefer_difficulty?: "easy" | "medium" | "hard" }`, response with `new_messages`. Use whichever route your backend exposes; behaviour is the same and both use v2.

---

### 3.4 POST `/sessions/{session_id}/evaluate-answer`

**When to use:** When you want to **only** evaluate the last answer (no next question in the same call), or in legacy flows that separate “submit answer” from “get next question”.

**Request (JSON body):**

```ts
{
  answer: string;   // The candidate’s answer text (required)
}
```

**Response (success):** `payload` includes:

```ts
{
  feedback: string;           // Feedback text (or redirect message)
  score?: number;             // 0–100 when it was a real evaluation
  dimension_tags?: string[]; // e.g. ["behavioral", "structure"]
  message_id: string;         // UUID of the stored FEEDBACK message
  redirect?: boolean;         // true if this was a greeting/off-topic redirect
}
```

If the user said something like “next question”, the backend may return a **next question** in the same response (see API_OVERVIEW or backend docs for that branch). That next question is also generated with v2 (role + difficulty curve).

**Errors:** `400` if there is no QUESTION in the session; `404` session not found; `503` if agent disabled.

---

## 4. Frontend usage summary

- **No new endpoints.** Keep using `POST .../chat` (or `.../send`) for the main flow and `POST .../next-question` when you only want the next question.
- **Role level:** Send `role_level` in **next-question** body when you know the user’s level (e.g. from profile or session setup). Values: `"INTERN"` | `"ASE"` | `"SSE"` | `"OTHER"`. Default is `ASE` if omitted. Same level is used for depth/expectations in **any** job domain (software, finance, etc.).
- **Difficulty:** You can show a badge or label using `message.meta.difficulty` on QUESTION messages (`easy` / `medium` / `hard`). By default questions follow the session curve (easier first, harder later). To **request a specific difficulty** (e.g. "Give me a hard question"), send `prefer_difficulty: "easy" | "medium" | "hard"` in the request body for **next-question**, **chat**, **send**, or **evaluate-answer** (when a next question is generated).
- **Question type:** Optional; use `message.meta.question_type` (`technical` / `behavioral` / `system_design`) for filters or labels.
- **Auth:** All session endpoints require `Authorization: Bearer <access_token>` (and the session must belong to the current user).

---

## 5. Quick copy-paste (TypeScript-ish types)

```ts
// Role level for next-question (optional in body)
type RoleLevel = "INTERN" | "ASE" | "SSE" | "OTHER";

// Next-question response payload
interface NextQuestionPayload {
  question: string;
  difficulty?: "easy" | "medium" | "hard";
  question_type?: "technical" | "behavioral" | "system_design";
  message_id: string;
}

// Optional difficulty override (when a next question is generated)
type PreferDifficulty = "easy" | "medium" | "hard";

// Next-question request body
interface NextQuestionRequest {
  question_type?: "technical" | "behavioral" | "system_design";
  role_level?: RoleLevel;
  prefer_difficulty?: PreferDifficulty;
}

// Chat/Send request
interface ChatRequest {
  content: string;
  prefer_difficulty?: PreferDifficulty;
}

// Message (in new_messages or from GET .../messages)
interface Message {
  id: string;
  session_id: string;
  sender: "USER" | "ASSISTANT";
  type: "QUESTION" | "ANSWER" | "FEEDBACK";
  content: string;
  meta: Record<string, string | undefined>;
  created_at: string;
  updated_at: string;
}

// Evaluate-answer response payload
interface EvaluateAnswerPayload {
  feedback: string;
  score?: number;
  dimension_tags?: string[];
  message_id: string;
  redirect?: boolean;
}
```

You can paste this doc (or the sections you need) into the frontend Cursor project so the AI and developers have a single reference for the new feature and the endpoints.
