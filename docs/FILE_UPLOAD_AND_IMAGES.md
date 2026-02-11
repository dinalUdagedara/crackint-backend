# File upload: PDF and images for resume and job extraction

Resume and job extraction both accept **PDF** or **images** (PNG, JPEG, WebP). Text is extracted from the file, then the same NER pipeline runs as for pasted text.

---

## 1. Supported file types

| Type   | Content-Type        | How text is obtained   |
|--------|---------------------|------------------------|
| PDF    | `application/pdf`   | PyMuPDF (direct text)  |
| PNG    | `image/png`         | Tesseract OCR          |
| JPEG   | `image/jpeg`, `image/jpg` | Tesseract OCR  |
| WebP   | `image/webp`        | Tesseract OCR          |

If the client sends `Content-Type: application/octet-stream`, the server infers the type from file magic bytes and uses PDF or OCR as appropriate.

**Size limit:** Same for all uploads (default 10 MB). See `MAX_UPLOAD_SIZE_MB` in config.

---

## 2. Where it’s used

| Endpoint | Accepts file? | Then |
|----------|----------------|------|
| **POST /api/v1/resumes/extract** | PDF or image | Extract text → resume NER → optional AI agent (`?validate=true`) → return entities (and persist). |
| **POST /api/v1/resumes/preview-extract** | PDF or image | Same extraction, no DB save. |
| **PUT /api/v1/resumes/{resume_id}** | PDF or image | Re-extract and update the resume record. |
| **POST /api/v1/jobs/extract** | PDF or image | Extract text → job poster NER (or empty entities if model not loaded) → return entities. No DB save. |

All of these also accept **raw text** via the `text` form field instead of a file. Send either file or text, not both.

---

## 3. OCR (images)

**Module:** `app/services/ocr.py`

Images are converted to text with **Tesseract OCR**. The service preprocesses images (grayscale, contrast boost, optional upscale) to improve results on posters and photos. Page segmentation is set to **PSM 3** (fully automatic) for multi-section layouts.

**Server requirement:** Tesseract must be installed on the machine running the backend.

- **macOS:** `brew install tesseract`
- **Ubuntu/Debian:** `apt install tesseract-ocr`
- **Windows:** Install from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki) and ensure `tesseract` is on PATH.

If Tesseract is not installed, image uploads return **400** with a message that Tesseract is required.

**Code:** `app/services/text_extraction.py` exposes **`extract_text_from_file(content, content_type)`**, which dispatches to PDF extraction or OCR. Resume and job services use this single entry point; they do not call PDF or OCR directly.

---

## 4. Frontend summary

- **Request:** `multipart/form-data` with either **file** (PDF or image) or **text** (raw string). Optional **validate=true** on resume endpoints for AI correction.
- **Response:** Same entity shape as when using pasted text. Resume: `NAME`, `EMAIL`, `SKILL`, `OCCUPATION`, `EDUCATION`, `EXPERIENCE`. Job: job-specific keys when the job poster model is loaded, otherwise empty `entities`.
- **Errors:** 400 if both file and text are sent, if file type is not supported, or if no text could be extracted (e.g. blank PDF or OCR failure).

For full API details (all endpoints, request/response schemas), see **API_SUMMARY_FOR_FRONTEND.md**. For resume pipeline details (NER, agent, config), see **docs/RESUME_EXTRACTION.md**.
