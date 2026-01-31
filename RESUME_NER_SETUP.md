# Resume NER model: save from Colab and use locally

The BERT-BiLSTM-CRF model is saved in Google Drive (e.g. `My Drive/resume_ner/`) when you run the save cell in the notebook. To use it in this backend, download that folder to your machine and point the app at it.

## Why the model is not in Git (industrial practice)

**Do not commit model files to the repo.** They are large binaries (~400 MB+), cause slow/failing pushes, and don’t belong in version control. The repo is for code and config; models are **artifacts** stored separately.

- **Local / dev:** Download the model (e.g. from Google Drive), put it in `model/resume_ner/` or any path, set `RESUME_NER_LOAD_DIR` in `.env`. The `model/` and `models/` folders are in `.gitignore`.
- **Production / team:** Store the model in **object storage** (AWS S3, Google Cloud Storage, Azure Blob) or a **model registry** (Hugging Face Hub, MLflow, Weights & Biases). The app or deploy pipeline downloads it at startup or at deploy time using `RESUME_NER_LOAD_DIR` or a dedicated “model download” step.
- **CI/CD:** In your pipeline, either mount the model from storage or run a step that downloads it before starting the API.

## 1. What to download

Download the **entire `resume_ner` folder** from Google Drive. It should contain:

- `bert_bilstm_crf_state.pt` – PyTorch model weights  
- `ner_config.json` – label tags, `bert_name`, `num_labels`  
- `vocab.txt` – BERT tokenizer vocabulary  
- `tokenizer_config.json`, `special_tokens_map.json` – tokenizer config  

## 2. How to download from Google Drive

**Option A – From Colab (easiest)**  
In a Colab cell, after saving the model to Drive:

```python
from google.colab import files
import zipfile, os

LOAD_DIR = "/content/drive/MyDrive/resume_ner"  # or your path
zip_path = "/content/resume_ner.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for name in os.listdir(LOAD_DIR):
        path = os.path.join(LOAD_DIR, name)
        if os.path.isfile(path):
            zf.write(path, f"resume_ner/{name}")
files.download(zip_path)
```

Then unzip `resume_ner.zip` on your laptop (e.g. into the backend project).

**Option B – From drive.google.com**  
1. Open [drive.google.com](https://drive.google.com), go to `My Drive` → `resume_ner`.  
2. Right‑click `resume_ner` → **Download** (Google zips the folder).  
3. Unzip the downloaded file on your machine.

**Option C – Google Drive for Desktop**  
If you use “Google Drive for Desktop”, the folder appears as a normal directory. Copy `resume_ner` from that directory into your backend project (e.g. `crackint-backend/models/resume_ner`).

## 3. Where to put it locally

Example layout:

```
crackint-backend/
  .env
  app/
  models/
    resume_ner/          ← put the downloaded folder here
      bert_bilstm_crf_state.pt
      ner_config.json
      vocab.txt
      tokenizer_config.json
      special_tokens_map.json
```

You can use any path you like (e.g. `~/models/resume_ner`); the app reads it from env.

## 4. Configure the backend

In `.env` (or your environment), set the path to that folder:

```env
# Absolute or relative to where you run the server
RESUME_NER_LOAD_DIR=/path/to/crackint-backend/models/resume_ner
```

Examples:

- macOS/Linux: `RESUME_NER_LOAD_DIR=/Users/you/Desktop/IIT/4th year/FYP/PROJECT/crackint-backend/models/resume_ner`  
- Windows: `RESUME_NER_LOAD_DIR=C:\Projects\crackint-backend\models\resume_ner`  
- Relative: `RESUME_NER_LOAD_DIR=./models/resume_ner` (run the server from the backend root)

If `RESUME_NER_LOAD_DIR` is not set or the path does not exist, the API still runs but uses rule-based fallbacks only (NAME/EMAIL from heuristics; no model-based SKILL/EDUCATION/EXPERIENCE/OCCUPATION).

## 5. Run the backend

From the backend root:

```bash
poetry install   # or: pip install -r requirements.txt
poetry run python server.py
```

Then call `POST /api/v1/resume/extract` with a PDF file or raw text; the response will include extracted entities using the loaded model when available.
