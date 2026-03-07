## Frontend Guide: Unified `chat` Endpoint for Prep Sessions

This doc explains how the frontend should use the **single** chat endpoint:

- `POST /api/v1/sessions/{session_id}/chat`

This replaces the need to manually call:

- `POST /sessions/{id}/messages`
- `POST /sessions/{id}/next-question`
- `POST /sessions/{id}/send`
- `POST /sessions/{id}/evaluate-answer`

for the **normal interview practice flow**. You can still use the lower-level endpoints for special tools or admin views, but for the main app, prefer `/chat`.

---

## 1. Endpoint overview

- **URL**: `/api/v1/sessions/{session_id}/chat`
- **Method**: `POST`
- **Auth**: Same as other session APIs (none yet, or whatever you add later).
- **Requires**: Session Q&A agent enabled (`SESSION_QA_AGENT_ENABLED=true` and `OPENAI_API_KEY` set).

### 1.1 Request body

```json
{
  "content": "The user's message for this turn (answer, greeting, or any text)."
}
```

- `content`:
  - Free-form text from the chat input.
  - Can be:
    - A greeting: `"hi"`, `"hello"`, `"thanks"`, etc.
    - A full interview answer.
    - A question like `"can you repeat the question?"`.

### 1.2 Response body

The response is wrapped in the standard `CommonResponse`:

```json
{
  "success": true,
  "message": "Chat turn processed.",
  "payload": {
    "new_messages": [
      {
        "id": "uuid-user",
        "session_id": "uuid-session",
        "sender": "USER",
        "type": "ANSWER",
        "content": "user message...",
        "meta": {}
      },
      {
        "id": "uuid-assistant-1",
        "session_id": "uuid-session",
        "sender": "ASSISTANT",
        "type": "FEEDBACK",
        "content": "Feedback or redirect...",
        "meta": {
          "score": "78",
          "dimension_tags": "behavioral,structure"
        }
      },
      {
        "id": "uuid-assistant-2",
        "session_id": "uuid-session",
        "sender": "ASSISTANT",
        "type": "QUESTION",
        "content": "Next interview question...",
        "meta": {
          "difficulty": "medium",
          "question_type": "technical"
        }
      }
    ]
  }
}
```

- `payload.new_messages`:
  - Ordered list of **all messages created in this turn**.
  - Each element matches the backend `MessageRead` shape.
  - You should **append them to the existing chat in order**.

---

## 2. Backend behaviour (what `/chat` does)

The backend centralises all interview logic behind `/chat`:

1. **Loads session context**
   - Finds the `PrepSession`, its `Resume` and `JobPosting` entities (if any), and existing messages.
   - Finds the **last `QUESTION` message** in this session (if any).

2. **Always stores the USER message**
   - Creates a `Message`:
     - `sender = "USER"`
     - `type = "ANSWER"`
     - `content = content`
     - `meta = {}`
   - Commits this message and includes it as the **first** entry in `new_messages`.

3. **Branch A: No previous QUESTION (starting the interview)**
   - If there is **no `QUESTION` yet**:
     - Treat this as “start the interview”.
     - Calls the Session Q&A question generator to create the **first interview question**.
     - Stores an ASSISTANT `QUESTION` message with difficulty / question_type metadata.
     - Appends that to `new_messages`.
   - The payload looks like:

```json
{
  "new_messages": [
    { "sender": "USER", "type": "ANSWER", "content": "hi, I want to practice" },
    { "sender": "ASSISTANT", "type": "QUESTION", "content": "First interview question?" }
  ]
}
```

4. **Branch B: There is a QUESTION (normal answer turn)**

   - The backend:
     1. Calls `classify_and_redirect(last_question, content)` to decide if this is a **greeting/off-topic** or a **substantive answer**.
     2. If **greeting/off-topic**:
        - Stores an ASSISTANT `FEEDBACK` message with `meta.redirect = "true"`.
        - Returns:

```json
{
  "new_messages": [
    { "sender": "USER", "type": "ANSWER", "content": "hi" },
    { "sender": "ASSISTANT", "type": "FEEDBACK", "content": "Hey! I'm here to help. When you're ready, answer the question above." }
  ]
}
```

        - No score, no new question in this branch.

     3. If **substantive answer**:
        - Calls `evaluate_answer(...)` to get `feedback`, `score (0–100)`, and `dimension_tags`.
        - Stores an ASSISTANT `FEEDBACK` message with:
          - `meta.score = "<score>"`
          - `meta.dimension_tags = "tag1,tag2,..."`
        - Optionally updates:
          - Session `summary.title` (once).
          - Session `summary.strengths` / `summary.areas_for_improvement` every N FEEDBACK messages.
        - Calls the question generator to get the **next** `QUESTION` and stores it.
        - Returns:

```json
{
  "new_messages": [
    {
      "sender": "USER",
      "type": "ANSWER",
      "content": "I led a migration project that reduced latency by 40%."
    },
    {
      "sender": "ASSISTANT",
      "type": "FEEDBACK",
      "content": "Good use of STAR. Add more metrics next time.",
      "meta": { "score": "78", "dimension_tags": "behavioral,structure" }
    },
    {
      "sender": "ASSISTANT",
      "type": "QUESTION",
      "content": "What is your greatest technical achievement?",
      "meta": { "difficulty": "medium", "question_type": "technical" }
    }
  ]
}
```

5. **Readiness score and summary**
   - `readiness_score` is **not** returned directly from `/chat`.
   - It is computed on `GET /sessions/{id}` or `GET /sessions/{id}/with-messages` from all FEEDBACKs’ scores.
   - Session `summary` (title, strengths, areas_for_improvement) is updated periodically inside the `/chat` flow and visible via those GETs.

---

## 3. Frontend usage patterns

### 3.1 TypeScript types

In `types/api.types.ts`, we already have:

```ts
export interface Message {
  id: string;
  session_id: string;
  sender: "USER" | "ASSISTANT";
  type: "QUESTION" | "ANSWER" | "FEEDBACK";
  content: string;
  metadata: { [key: string]: string };
  created_at: string;
  updated_at: string;
}

export interface ChatTurnPayload {
  new_messages: Message[];
}
```

And in `services/sessions.service.ts`:

```ts
export async function postChatTurn(
  sessionId: string,
  content: string
): Promise<ApiResponse<ChatTurnPayload>> {
  const res = await fetch(`${SESSIONS_BASE}/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  return parseResponse<ChatTurnPayload>(res);
}
```

### 3.2 Basic flow in the chat view

1. **On mount**:
   - Call `GET /api/v1/sessions/{id}/with-messages` once to hydrate:
     - Session meta (title, readiness_score, summary).
     - Full `messages[]` history.

2. **On user send**:
   - Call `POST /api/v1/sessions/{id}/chat` with `{ content: userText }`.
   - On success:
     - Read `payload.new_messages`.
     - Append those to the existing `messages` in state.
   - Example (as implemented in `SessionChatView`):

```ts
const chatMutation = useMutation({
  mutationFn: async (content: string) => {
    const res = await postChatTurn(sessionId, content.trim());
    if (!res.success || !res.payload) {
      throw new Error(res.message || "Failed to send message.");
    }
    return res.payload;
  },
  onSuccess: (payload) => {
    setInput("");
    if (session && payload?.new_messages?.length) {
      setSession({
        ...session,
        messages: [...session.messages, ...payload.new_messages],
      });
    } else {
      // Fallback: refetch full session
      refreshSession();
    }
  },
});
```

3. **Optionally refresh meta**:
   - After some turns, you can call `GET /sessions/{id}` or `GET /sessions/{id}/with-messages` again to:
     - Show updated `readiness_score`.
     - Show updated `summary.strengths` / `summary.areas_for_improvement`.

---

## 4. UX guidelines

- **First turn**:
  - You do **not** need a separate “Ask first question” button.
  - The first time the user types anything (even just “Hi”), `/chat` will:
    - Store their message.
    - Generate the first question.
    - Return `[USER ANSWER, ASSISTANT QUESTION]`.

- **Greeting/off-topic messages**:
  - When the user sends “hi”, “thanks”, or similar while a question is on-screen:
    - `/chat` returns `[USER ANSWER, ASSISTANT FEEDBACK redirect]`.
    - Show this feedback as a normal assistant bubble, but **do not** show any score UI (no score is attached).

- **Evaluation feedback**:
  - When the user answers the question:
    - `/chat` returns `[USER ANSWER, ASSISTANT FEEDBACK, ASSISTANT QUESTION]`.
    - You can:
      - Highlight the feedback bubble (different color).
      - Surface `score` and `dimension_tags` from `metadata` if you want (you can read them by re-fetching `/with-messages` or by inspecting the newly appended `FEEDBACK` message’s metadata after a refresh).

- **Error states**:
  - `404` → invalid session ID: show “Session not found”.
  - `503` → Session Q&A disabled / LLM failure: show a banner like:
    - “Interview coach is temporarily unavailable. You can still type notes here, but feedback might be delayed.”
    - Optionally fall back to storing messages via `/messages` only.

---

## 5. Migration notes (for existing frontend code)

If your frontend was previously using:

- `POST /sessions/{id}/messages` + `POST /sessions/{id}/evaluate-answer`, or
- `POST /sessions/{id}/send`,

the migration steps are:

1. **Stop** calling `/messages` and `/evaluate-answer` directly from the chat UI.
2. **Stop** calling `/send` from the chat UI.
3. Use just:

```ts
const resp = await postChatTurn(sessionId, userInput);
const newMessages = resp.payload?.new_messages ?? [];
setSession((prev) =>
  prev
    ? { ...prev, messages: [...prev.messages, ...newMessages] }
    : prev,
);
```

The lower-level endpoints (`next-question`, `send`, `evaluate-answer`) remain available for:

- Admin tools.
- Analytics or batch operations.
- Any future flows where you explicitly want to control when questions are generated vs when answers are evaluated.

