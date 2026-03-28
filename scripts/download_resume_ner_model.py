"""
Download the Resume NER model from Hugging Face and prepare it for the backend.

Usage:
    pip install huggingface_hub   # or: poetry add huggingface_hub
    python scripts/download_resume_ner_model.py

Then set in .env:
    RESUME_NER_LOAD_DIR=./model/resume_ner
"""
from pathlib import Path
import zipfile
import sys

def main() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Install huggingface_hub first: pip install huggingface_hub")
        sys.exit(1)

    repo_id = "dinalUdagedara/resume-entity-extractor"
    local_dir = Path(__file__).resolve().parent.parent / "model" / "resume_ner"
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {repo_id} to {local_dir} ...")
    snapshot_download(repo_id=repo_id, local_dir=str(local_dir))

    # Unzip the model weights if present (HF repo has .pt inside a zip)
    for z in local_dir.glob("*.zip"):
        print(f"Unzipping {z.name} ...")
        with zipfile.ZipFile(z, "r") as zf:
            for name in zf.namelist():
                zf.extract(name, local_dir)
                # If zip contains a subdir (e.g. resume_ner/bert_bilstm_crf_state.pt), move .pt up
                p = local_dir / name
                if p.is_file() and name.count("/") == 1 and name.endswith(".pt"):
                    target = local_dir / Path(name).name
                    if target != p:
                        target.write_bytes(p.read_bytes())
                        p.unlink()
        break

    # Ensure we have the expected file (backend needs bert_bilstm_crf_state.pt in load_dir)
    pt_files = list(local_dir.glob("**/bert_bilstm_crf_state.pt"))
    if pt_files:
        pt = pt_files[0]
        if pt.parent != local_dir:
            (local_dir / "bert_bilstm_crf_state.pt").write_bytes(pt.read_bytes())
            pt.unlink()

    print(f"Done. Set in .env:\n  RESUME_NER_LOAD_DIR={local_dir.resolve()}")
    print("Or relative from project root:\n  RESUME_NER_LOAD_DIR=./model/resume_ner")

if __name__ == "__main__":
    main()
