# Frontend Guide: Conversational Tutor Mode (`TUTOR_CHAT`)

We have added a new mode to Prep Sessions called `TUTOR_CHAT`. This mode allows the user to have a free-flowing, ChatGPT-style conversation with the career coach without being forced into a strict Q&A interview format.

The best part: **It uses the exact same API endpoints you are already using.**

## 1. Type Updates Needed

First, update your frontend `SessionMode` types to include the new mode.

```ts
// Update your existing SessionMode enum/type
export type SessionMode = "TARGETED" | "QUICK_PRACTICE" | "TUTOR_CHAT";
```

## 2. Creating a Tutor Chat Session

To start a conversational session, call the standard session creation endpoint but pass `TUTOR_CHAT` as the mode.

- **Endpoint**: `POST /api/v1/sessions`
- **Request Body**:
```json
{
  "user_id": "uuid-or-null",
  "resume_id": "uuid-or-null",       // Optional: Context for the coach
  "job_posting_id": "uuid-or-null",  // Optional: Context for the coach
  "mode": "TUTOR_CHAT"
}
```
*Note: If you provide a `resume_id` or `job_posting_id`, the LLM coach will automatically know about the user's skills and the job they are applying for, making its advice highly personalized.*

## 3. Chatting with the Tutor

Use the exact same unified chat endpoint that you use for standard interviews. 

- **Endpoint**: `POST /api/v1/sessions/{session_id}/chat`
- **Request Body**:
```json
{
  "content": "Hi! Can you give me some tips on how to introduce myself?"
}
```

### Backend Behavior in `TUTOR_CHAT` Mode:
Unlike `TARGETED` mode (which generates an interview question, waits for an answer, and scores it), the `TUTOR_CHAT` mode simply acts like ChatGPT:
1. It reads the full chat history.
2. It replies directly to the user's question.
3. It **does not** generate an interview question (unless the user explicitly asks it to).
4. It **does not** evaluate or score the answer.

### The Response Shape:
The response will contain exactly two messages: the User's message, and the Assistant's reply.

```json
{
  "success": true,
  "message": "Chat turn processed: tutor reply generated.",
  "payload": {
    "new_messages": [
      {
        "id": "uuid-user-msg",
        "sender": "USER",
        "type": "ANSWER",
        "content": "Hi! Can you give me some tips...",
        "meta": {}
      },
      {
        "id": "uuid-assistant-reply",
        "sender": "ASSISTANT",
        "type": "FEEDBACK",
        "content": "Absolutely! When introducing yourself, you should focus on...",
        "meta": {
          "redirect": "true"
        }
      }
    ]
  }
}
```

## 4. UI Implementation Details (Important)

Notice that the Assistant's message comes back as `type: "FEEDBACK"` and includes `"meta": { "redirect": "true" }`. 

If your frontend is already handling the "redirect/off-topic" messages correctly from the normal interview flow, **you don't need to change any UI code!**

**Checklist for the UI:**
- ✅ Treat `type: "FEEDBACK"` with `meta.redirect === "true"` as a standard chat bubble.
- ✅ **Do not** attempt to display a score (like `78/100`) or dimension tags, because the coach is just chatting, not grading. (No score is returned anyway).
- ✅ Append the `new_messages` to your chat history state exactly as you do now.
