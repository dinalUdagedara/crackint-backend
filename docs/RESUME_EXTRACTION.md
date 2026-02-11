# Resume entity extraction: current approach

This document describes how the Crackint backend extracts entities (NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE) from resume text or PDFs.

---

## 1. Overview

- **Input:** Raw resume text (e.g. from PDF extraction) or pasted text.
- **Output:** A structured dict with six entity types, each a list of strings (e.g. `{"NAME": ["John Doe"], "SKILL": ["Python", "SQL"], ...}`).
- **Approach:** Hybrid — rule-based extraction for NAME and EMAIL; neural NER (BiLSTM-CRF) for SKILL, OCCUPATION, EDUCATION, and EXPERIENCE. The backend supports two model architectures; format is detected automatically from the model directory and config.

---

## 2. Supported model formats

The app detects which model type to load from the contents of `RESUME_NER_LOAD_DIR` (or the download cache).

### 2.1 Word2Vec + BiLSTM + CRF (current default)

- **Config:** `ner_config.json` must contain `word2id`, `embed_dim`, and `num_labels`; state file must be `bilstm_crf_state.pt`.
- **Architecture:** Embedding layer (vocab size × embed_dim) → BiLSTM → linear → CRF. The **full checkpoint** (including `embed.weight`) is loaded so inference matches the training/Colab setup.
- **Tokenization:** Input text is split into tokens by whitespace (`re.findall(r"\S+", text)`). Each token is mapped to an ID via `word2id` (exact match only; unknown tokens use `<UNK>`). Sequence length is capped by `max_len` from config (default 256).
- **Use case:** Lighter than BERT; same behaviour as the Path2 FYP notebook when the same checkpoint and `word2id` are used.

### 2.2 BERT + BiLSTM + CRF

- **Config:** `ner_config.json` with `tags`, `bert_name`, `num_labels`; state file `bert_bilstm_crf_state.pt`; BERT tokenizer files in the same directory (`vocab.txt`, `tokenizer_config.json`, `special_tokens_map.json`).
- **Architecture:** BERT (e.g. bert-base-uncased) → BiLSTM → linear → CRF. Subword tokenization; first subword index per original word is used to align model output to words.
- **Use case:** When the model was trained with BERT in the pipeline (e.g. Hugging Face–style setup).

---

## 3. Model loading

- **Source:** A single directory on disk (e.g. `model/resume_ner/`). The app does not train; it only loads a pre-trained checkpoint and config.
- **Resolution order:**
  1. If `RESUME_NER_LOAD_DIR` is set and that path exists → load from that directory.
  2. Else if `RESUME_NER_GDRIVE_FOLDER_ID` or `RESUME_NER_GDRIVE_FILE_ID` is set → download from Google Drive into `model/resume_ner` (if not already present), then load from there.
  3. Else → no model; extraction uses rule-based fallback only (NAME and EMAIL from heuristics/rules; other keys empty).
- **State file:** For Word2Vec path the full state dict (including `embed.weight`) is loaded so embeddings match the training checkpoint. For BERT path the BERT weights come from the Hugging Face model; the checkpoint supplies BiLSTM + CRF + projection.
- **Startup log:** On startup the server prints whether the model was loaded from a local path or from the Drive cache, and for Word2Vec it prints embed_dim, hidden_dim, and vocab size.

See **RESUME_NER_SETUP.md** for how to obtain the model (Google Drive, Hugging Face, or local) and set env vars.

---

## 4. Input pipeline

- **PDF:** Bytes are passed to `extract_text_from_pdf` (e.g. PyMuPDF). The returned string is the only input to NER; no layout or structure is used.
- **Pasted text:** The client sends the raw string (e.g. via form field `text`); it is stripped and passed to the same NER path.
- **No extra normalization:** Aside from stripping and tokenization (per model type), the backend does not lowercasing or sentence segmentation. The exact string (after PDF extraction or paste) is what the model sees.

---

## 5. Hybrid extraction logic

High-level flow (see `parse_resume_hybrid` in `app/ml/resume_ner.py`):

1. **If no model is loaded:** Return `_stub_entities(text)` (first line as NAME candidate; simple email regex; other keys empty). No NER.
2. **If model is loaded:**
   - Run **rule-based** NAME and EMAIL:
     - **NAME:** `_extract_name_heuristic(text)` — among the first few lines, take a short line (1–4 words, title case, no `@`/URL) as the name.
     - **EMAIL:** `_extract_email_rules(text)` — regex for `...@....`; deduplicated list.
   - Run **model** on the full text: `_parse_resume(text)` → word-level (or subword-aligned) tags, then build entities from B-/I- spans.
   - **Overwrite:** Set `entities["NAME"]` and `entities["EMAIL"]` to the rule-based results, so NAME and EMAIL always come from rules when the model is loaded; the model still runs for SKILL, OCCUPATION, EDUCATION, EXPERIENCE.

So the **model is used only for** SKILL, OCCUPATION, EDUCATION, and EXPERIENCE; NAME and EMAIL are deterministic rules for stability and to avoid NER errors on those fields.

---

## 6. NER inference and entity building

- **Tokenization:** As in §2 (Word2Vec: `word2id` exact match, max_len; BERT: tokenizer, first subword index per word).
- **Model:** Forward pass returns a tag index per token (or per word, via first subword for BERT). Indices are mapped with `id2label` (e.g. O, B-NAME, I-NAME, B-SKILL, I-SKILL, …).
- **Span building:** Over the word-level tag sequence:
  - **B-X:** Start a new span of type X; consume following **I-X** tokens; append the phrase (space-joined) to `entities[X]`.
  - **I-X** at the start of an X-span (no preceding B-X or I-X): treat as start of a new span (leading I-X) and consume up to the next non-I-X.
  - **O:** Skip.
- **Normalization:** `_normalize_entities` strips trailing punctuation from each phrase, deduplicates by (type, lowercased value), and preserves order. Output keys are always: NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE.

---

## 7. Output shape

Every response uses the same structure:

```json
{
  "NAME": ["..."],
  "EMAIL": ["...", "..."],
  "SKILL": ["...", "..."],
  "OCCUPATION": ["..."],
  "EDUCATION": ["...", "..."],
  "EXPERIENCE": ["..."]
}
```

Lists may be empty. NAME and EMAIL are from rules; the rest are from the NER model (or empty if no model or model predicts O everywhere).

---

## 8. API endpoints

- **POST /api/v1/resumes/extract**  
  Accepts either a PDF file (multipart `file`) or pasted text (form field `text`). Runs the full pipeline (PDF → text if needed, then hybrid extraction), persists a resume record, and returns `entities` and `raw_text` (the exact string passed to the model).

- **POST /api/v1/resumes/preview-extract**  
  Same input (file or text). Returns `extracted_text` and `entities` **without** saving to the database. Use this to inspect the text the model receives and the extracted entities.

Both endpoints return the same entity structure; the only difference is persistence and the response field names (`raw_text` vs `extracted_text`).

---

## 9. Configuration

| Env var | Purpose |
|--------|--------|
| `RESUME_NER_LOAD_DIR` | Directory containing the model (e.g. `./model/resume_ner`). If set and path exists, this is used. |
| `RESUME_NER_GDRIVE_FOLDER_ID` | Google Drive folder ID. Used only when `RESUME_NER_LOAD_DIR` is unset or path does not exist; triggers download into the default cache dir. |
| `RESUME_NER_GDRIVE_FILE_ID` | Google Drive file ID (e.g. zip). Same as above for a single file. |

Optional download dependency: `gdown` (e.g. `poetry install --with download`). Required only when using the GDrive env vars.

---

## 10. File layout (Word2Vec model)

Minimum for the Word2Vec path:

- `ner_config.json` — must include `tags`, `word2id`, `embed_dim`, `num_labels`, and optionally `max_len`.
- `bilstm_crf_state.pt` — PyTorch state dict (embed, LSTM, fc, CRF). The **full** state is loaded so embeddings match training/Colab.

The `word2vec.model` file is **not** used at inference time; the checkpoint’s `embed.weight` is used.

---

## 11. References

- **RESUME_NER_SETUP.md** — Where to store the model (Drive, Hugging Face, S3), how to download, and env setup.
- **app/ml/resume_ner.py** — Implementation: model classes, `load_model`, `_parse_resume`, `parse_resume_hybrid`, rules and normalization.
- **app/api/resume/route.py** — Extract and preview-extract endpoints; PDF vs text handling.
- **app/api/resume/service.py** — Orchestration: PDF text extraction and call to `parse_resume_hybrid`.
