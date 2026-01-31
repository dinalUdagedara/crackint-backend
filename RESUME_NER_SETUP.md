# Resume NER model: save from Colab and use locally

The BERT-BiLSTM-CRF model is saved in Google Drive (e.g. `My Drive/resume_ner/`) when you run the save cell in the notebook. To use it in this backend, download that folder to your machine and point the app at it.

## Why the model is not in Git (industrial practice)

**Do not commit model files to the repo.** They are large binaries (~400 MB+), cause slow/failing pushes, and don’t belong in version control. The repo is for code and config; models are **artifacts** stored separately.

- **Local / dev:** Download the model (e.g. from Google Drive), put it in `model/resume_ner/` or any path, set `RESUME_NER_LOAD_DIR` in `.env`. The `model/` and `models/` folders are in `.gitignore`.
- **Production / team:** Store the model in **object storage** (AWS S3, Google Cloud Storage, Azure Blob) or a **model registry** (Hugging Face Hub, MLflow, Weights & Biases). The app or deploy pipeline downloads it at startup or at deploy time using `RESUME_NER_LOAD_DIR` or a dedicated “model download” step.
- **CI/CD:** In your pipeline, either mount the model from storage or run a step that downloads it before starting the API.

---

## Where to store the model (and which is most suitable)

| Place | Best for | Pros | Cons |
|-------|----------|------|------|
| **Google Drive** | You already use Colab; sharing with 1–2 people | No extra account, already in your workflow | Manual download; not ideal for production/CI |
| **Hugging Face Hub** | Team, reproducibility, any env (dev/CI/prod) | Free, versioned, one-line download in code | Public by default (use private repo if needed) |
| **AWS S3 / GCS / Azure Blob** | Production, CI/CD, “enterprise” | Standard in industry, works with every deploy pipeline | Need cloud account; small cost for storage/egress |

**Recommendation:**

- **FYP / solo or small team:** Keep using **Google Drive** (save from Colab, download to your machine, set `RESUME_NER_LOAD_DIR`). Easiest.
- **Want one place for code + model + others:** Use **Hugging Face Hub** — upload once, then anyone or any server can download with a small script (see below).
- **Production / deployed app:** Use **S3 or GCS** — upload the model once, then the app or deploy step downloads it to a local directory and sets `RESUME_NER_LOAD_DIR`.

The backend always loads from a **directory on disk**; “saving the model somewhere” means storing that directory’s contents in one of the above, then either copying them to disk by hand or with a download step.

---

## How to save and use the model per option

### Option 1: Google Drive (simplest — you already have this)

- **Save:** In Colab, save the model to Google Drive (e.g. `My Drive/resume_ner/`).
- **Use locally:** Download that folder (zip from Drive or Colab script in section 2 below), unzip to e.g. `model/resume_ner/`, set `RESUME_NER_LOAD_DIR=./model/resume_ner` in `.env`.
- **Share with teammate:** Share the Drive folder or the zip; they download and set `RESUME_NER_LOAD_DIR` the same way.

No code changes; the “storage” is just Drive, the “loading” is manual copy + env var.

---

### Option 2: Hugging Face Hub (good for team and automation)

**This project’s model repo:** [dinalUdagedara/resume-entity-extractor](https://huggingface.co/dinalUdagedara/resume-entity-extractor)

- **Save (upload once):**  
  1. Create a repo on [huggingface.co](https://huggingface.co) (e.g. `your-username/resume-entity-extractor`).  
  2. Upload the `resume_ner` files: zip with the `.pt` weights + `ner_config.json`, `vocab.txt`, `tokenizer_config.json`, `special_tokens_map.json` at repo root (or use the CLI).

- **Use (download then load):**  
  On any machine (or in CI), run the download script, then set `.env` and start the backend:

  ```bash
  # Install download dependency (one time)
  poetry install --with download
  # or: pip install huggingface_hub

  # Download model from Hugging Face to ./model/resume_ner
  python scripts/download_resume_ner_model.py

  # Set in .env (or export)
  # RESUME_NER_LOAD_DIR=./model/resume_ner

  poetry run python server.py
  ```

  The script fetches `dinalUdagedara/resume-entity-extractor`, unzips any zip into `model/resume_ner`, and prints the exact path to put in `RESUME_NER_LOAD_DIR`.

**Important:** The backend needs **`bert_bilstm_crf_state.pt`** (the PyTorch weights, ~400 MB+) in that folder. If your Hugging Face repo only has config/tokenizer files and a small zip, upload **`bert_bilstm_crf_state.pt`** to the repo (Files and versions → Upload file). Then re-run the download script so the .pt is present in `model/resume_ner/`. Without the .pt file, the API runs in rule-based fallback only (NAME and EMAIL; SKILL, EDUCATION, EXPERIENCE, OCCUPATION will be empty).

- **Most suitable when:** You want one canonical place for the model that both people and servers can use without manual Drive downloads.

---

### Option 3: AWS S3 / Google Cloud Storage (production)

- **Save:** Zip the `resume_ner` folder and upload to a bucket, e.g.  
  - **S3:** `s3://your-bucket/crackint/resume_ner/v1/resume_ner.zip`  
  - **GCS:** `gs://your-bucket/crackint/resume_ner/v1/resume_ner.zip`

  Use the AWS CLI, `gsutil`, or the cloud console. Version by path (e.g. `v1/`, `v2/`).

- **Use:** Before starting the API, download and unzip to a local directory, then set `RESUME_NER_LOAD_DIR`:

  ```bash
  # Example (S3): download and unzip
  aws s3 cp s3://your-bucket/crackint/resume_ner/v1/resume_ner.zip .
  unzip -o resume_ner.zip -d ./model/
  export RESUME_NER_LOAD_DIR=./model/resume_ner
  python server.py
  ```

  In production, this is often a step in your Dockerfile or deploy pipeline; the app always reads from a local path.

- **Most suitable when:** The app runs in AWS/GCP/Azure and you want the model in the same cloud, with access control and no manual steps.

---

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
