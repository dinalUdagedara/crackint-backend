## Frontend Upgrade Guide: Single `send` Endpoint for Session Chat

This doc explains how to upgrade the frontend from the **two-call** flow:

- `POST /sessions/{id}/messages` (USER answer)
- `POST /sessions/{id}/evaluate-answer` (LLM feedback)

to the new **single-call** flow:

- `POST /sessions/{id}/send` (store user message + get assistant response).

The goal is to make the chat feel more like ChatGPT: one “send” per user turn.

> **Note:** There is now an even higher-level `POST /sessions/{id}/chat` endpoint that combines:
> - Storing the user message
> - Evaluating answers (or redirecting greetings/off-topic)
> - And, when appropriate, asking the **next question** in the same call.
>
> For most new frontend work, prefer the **unified** `/chat` endpoint. The `/send` endpoint remains a useful lower-level building block when you want to control when questions are asked.

---

## 1. New endpoint: `POST /sessions/{id}/send`

- **URL**: `/api/v1/sessions/{session_id}/send`
- **Method**: `POST`
- **Body**:

```json
{
  "content": "The user's message (answer or any text)."
}
```

- **Response** (`CommonResponse<SendReplyPayload>`):

```json
{
  "success": true,
  "message": "Reply sent and feedback stored.",
  "payload": {
    "user_message_id": "uuid-of-stored-user-message",
    "feedback": "Assistant text (redirect or evaluation feedback).",
    "score": 78,
    "dimension_tags": ["behavioral", "communication", "structure"],
    "message_id": "uuid-of-stored-feedback-message",
    "redirect": false
  }
}
```

**Field meanings:**

- `user_message_id`: ID of the stored USER `ANSWER` message.
- `feedback`: Assistant text.
  - If `redirect === true`: this is a short, friendly redirect (e.g. “Hey! I’m here to help. When you’re ready, answer the question above…”).
  - If `redirect === false`: this is evaluation feedback.
- `score`:
  - Number `0–100` when `redirect === false`.
  - `null` (or missing in some clients) when `redirect === true`.
- `dimension_tags`: Tags from evaluation (e.g. `["technical", "structure"]`); empty for redirects.
- `message_id`: ID of the stored ASSISTANT `FEEDBACK` message.
- `redirect`: `true` if the message was treated as greeting/off-topic, `false` if it was evaluated as a real answer.

---

## 2. Backend behavior (high level)

When the frontend calls `POST /sessions/{id}/send`:

1. **Validate session + last question**
   - The backend loads the session and finds the last `QUESTION` message.
   - If **no question exists**, it returns `400`:
     - Detail: “No question in this session to reply to. Add a question first (e.g. via next-question).”

2. **Store USER message**
   - Creates a `Message`:
     - `sender = "USER"`
     - `type = "ANSWER"`
     - `content = body.content`
     - `meta = {}`
   - Commits and returns `user_message_id`.

3. **Decide: redirect vs evaluation**
   - Calls `classify_and_redirect(last_question, body.content)`:
     - For obvious greetings (e.g. “hi”, “hello”, “thanks”) → **instant redirect** (no LLM).
     - For borderline/off-topic (“I don’t know”, “hint?”, small talk) → one LLM call to generate a short, warm redirect.
     - For real answers → returns `None` (go to full evaluation).

4. **If redirect (greeting/off-topic)**
   - Stores an ASSISTANT `FEEDBACK` message:
     - `sender = "ASSISTANT"`
     - `type = "FEEDBACK"`
     - `content = redirect text`
     - `meta.redirect = "true"`
   - Returns payload with:
     - `redirect = true`
     - `score = null`
     - `dimension_tags = []`

5. **If real answer (evaluation)**
   - Calls `evaluate_answer(question, answer, ...)`:
     - Gets `feedback`, `score (0–100)`, `dimension_tags`.
   - Stores an ASSISTANT `FEEDBACK` message with:
     - `meta.score = "<score>"`
     - `meta.dimension_tags = "tag1,tag2,..."`
   - Optionally updates:
     - `summary.title` once (session title).
     - `summary.strengths` / `summary.areas_for_improvement` every N feedbacks.
   - Returns payload with:
     - `redirect = false`
     - `score` and `dimension_tags` populated.

Readiness score is still computed on GET from all FEEDBACK scores; redirects (no score) are ignored.

---

## 3. New recommended frontend flow

### 3.1 Starting a session

1. **Create session** (unchanged):
   - `POST /api/v1/sessions` with `user_id`, `resume_id`, `job_posting_id`, `mode`.

2. **Get the first question** (recommended):
   - Call `POST /api/v1/sessions/{id}/next-question`.
   - Render the returned ASSISTANT `QUESTION` message in the chat.

   Alternatively, you can manually add an initial `QUESTION` via `POST /sessions/{id}/messages`, but `next-question` is the normal path.

3. **Enable chat input** only once a `QUESTION` exists.
   - Before that, show a CTA like “Click ‘Ask next question’ to start”.

### 3.2 Sending a user message (single call)

When the user types into the chat box:

1. **Do not** call `POST /messages` directly.
2. Instead, call:

```ts
await client.post(`/api/v1/sessions/${sessionId}/send`, {
  content: userText,
});
```

3. On success:
   - Append **two** messages in the UI:
     - **User message**:
       - `id = payload.user_message_id`
       - `sender = "USER"`
       - `type = "ANSWER"`
       - `content = userText` (you already know this).
     - **Assistant message**:
       - `id = payload.message_id`
       - `sender = "ASSISTANT"`
       - `type = "FEEDBACK"`
       - `content = payload.feedback`
       - If `payload.redirect === false`:
         - Show `payload.score` and `payload.dimension_tags` somewhere in the UI.

4. Optionally:
   - Re-fetch `GET /sessions/{id}` or `GET /sessions/{id}/with-messages` to refresh:
     - `readiness_score`
     - `summary` (title, strengths, areas_for_improvement)

---

## 4. Error handling & UX tips

### 4.1 No question yet (400 from `/send`)

If the frontend calls `/send` before a `QUESTION` exists in the session, the backend returns `400`:

- **Cause**: User tried to answer before starting the interview.
- **Frontend behavior**:
  - Show a friendly message like:
    - “Let’s start with a question first. Click ‘Ask next question’ to begin.”
  - Disable the chat input until there is at least one `QUESTION` in the message list.

### 4.2 Greeting/off-topic messages

When `redirect === true`:

- Treat it as a **normal assistant chat bubble**, but:
  - Don’t show score or tags.
  - Optionally annotate in UI that this isn’t “graded feedback” (it’s just guidance).

You can choose to visually de-emphasize redirects (smaller text, no score chip, etc.) so users understand it’s not an evaluation of their answer.

### 4.3 Network / 503 errors

When Session Q&A is disabled or the LLM fails, `/send` can return `503` (same as other Q&A endpoints).

- Frontend should:
  - Show a fallback message: “Interview coach is temporarily unavailable. You can still write notes here, but feedback might be delayed.”
  - Optionally allow plain chat via `/messages` without feedback.

---

## 5. Migration from the old two-call flow

Previously, the flow for each user answer was:

1. `POST /sessions/{id}/messages` with:
   - `sender = "USER"`, `type = "ANSWER"`, `content = answer`.
2. `POST /sessions/{id}/evaluate-answer` with:
   - `{ "answer": "same text" }`.

To migrate:

- **Remove** the explicit `POST /messages` call for user answers.
- **Replace** the `POST /evaluate-answer` call with a single `POST /send`:

```ts
// OLD
await client.post(`/api/v1/sessions/${id}/messages`, {
  sender: "USER",
  type: "ANSWER",
  content: answer,
  metadata: {},
});
const resp = await client.post(`/api/v1/sessions/${id}/evaluate-answer`, {
  answer,
});

// NEW
const resp = await client.post(`/api/v1/sessions/${id}/send`, {
  content: answer,
});
```

- Update the chat rendering to use `SendReplyPayload`:
  - Use `payload.user_message_id` for the USER bubble.
  - Use `payload.message_id`, `payload.feedback`, `payload.score`, `payload.dimension_tags`, `payload.redirect` for the ASSISTANT bubble.

You can keep `POST /evaluate-answer` as a **fallback** or for any internal tools, but the user-facing app should prefer `POST /send` for all chat turns.

