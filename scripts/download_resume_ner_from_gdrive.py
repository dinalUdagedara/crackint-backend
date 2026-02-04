#!/usr/bin/env python3
"""
Download the Resume NER model from Google Drive and prepare it for the backend.

Usage:
    pip install gdown   # or: poetry install --with download
    python scripts/download_resume_ner_from_gdrive.py [FOLDER_ID]
    python scripts/download_resume_ner_from_gdrive.py --file FILE_ID   # single zip file

    Or set env: RESUME_NER_GDRIVE_FOLDER_ID=... or RESUME_NER_GDRIVE_FILE_ID=...

Then set in .env:
    RESUME_NER_LOAD_DIR=./model/resume_ner
"""
from pathlib import Path
import shutil
import zipfile
import sys
import os
import argparse

# Default folder ID (shared "Anyone with the link"): resume_ner folder on Drive
DEFAULT_FOLDER_ID = "1n3ErPwIo9fpLTuWzuBSG46JOMqlNpB_X"


def _flatten_and_unzip(local_dir: Path) -> None:
    """Move files from subfolders into local_dir; unzip any .zip and move .pt/config out."""
    local_dir = local_dir.resolve()
    for item in list(local_dir.iterdir()):
        if item.is_dir():
            for f in item.iterdir():
                if f.is_file():
                    dest = local_dir / f.name
                    if not dest.exists() or f.stat().st_size != dest.stat().st_size:
                        shutil.copy2(f, dest)
            shutil.rmtree(item, ignore_errors=True)
        elif item.suffix.lower() == ".zip":
            with zipfile.ZipFile(item, "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    zf.extract(name, local_dir)
                    extracted = local_dir / name
                    if extracted.is_file() and extracted.parent != local_dir:
                        target = local_dir / Path(name).name
                        if target != extracted:
                            shutil.move(str(extracted), str(target))
            item.unlink()
    # Flatten one more time in case zip had a single top-level dir
    for item in list(local_dir.iterdir()):
        if item.is_dir():
            for f in item.iterdir():
                if f.is_file():
                    dest = local_dir / f.name
                    if not dest.exists():
                        shutil.copy2(f, dest)
            shutil.rmtree(item, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Resume NER model from Google Drive")
    parser.add_argument("id", nargs="?", default=None, help="Folder ID (default from env or built-in)")
    parser.add_argument("--file", "-f", metavar="FILE_ID", help="Download a single zip file by File ID")
    args = parser.parse_args()

    file_id = (os.environ.get("RESUME_NER_GDRIVE_FILE_ID", "").strip() or args.file) or None
    folder_id = None
    if not file_id:
        folder_id = os.environ.get("RESUME_NER_GDRIVE_FOLDER_ID", "").strip() or args.id or DEFAULT_FOLDER_ID

    if not folder_id and not file_id:
        print("Usage: python scripts/download_resume_ner_from_gdrive.py [FOLDER_ID]")
        print("       python scripts/download_resume_ner_from_gdrive.py --file FILE_ID")
        print("   or set RESUME_NER_GDRIVE_FOLDER_ID or RESUME_NER_GDRIVE_FILE_ID in the environment")
        sys.exit(1)

    try:
        import gdown
    except ImportError:
        print("Install gdown first: pip install gdown  or  poetry install --with download")
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    local_dir = project_root / "model" / "resume_ner"
    local_dir.mkdir(parents=True, exist_ok=True)

    download_dir = project_root / "model" / "resume_ner_download"
    if download_dir.exists():
        shutil.rmtree(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        if file_id:
            print(f"Downloading file {file_id} from Google Drive ...")
            zip_path = download_dir / "resume_ner.zip"
            gdown.download(id=file_id, output=str(zip_path), quiet=False, use_cookies=False)
        else:
            print(f"Downloading folder {folder_id} from Google Drive to {download_dir} ...")
            gdown.download_folder(
                id=folder_id,
                output=str(download_dir),
                quiet=False,
                use_cookies=False,
            )
    except Exception as e:
        print(f"Download failed: {e}")
        if download_dir.exists():
            shutil.rmtree(download_dir, ignore_errors=True)
        sys.exit(1)

    # Flatten: move all files into local_dir, unzip any zips
    for f in download_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(download_dir)
            dest = local_dir / rel.name
            if f != dest:
                shutil.copy2(f, dest)
    _flatten_and_unzip(local_dir)
    shutil.rmtree(download_dir, ignore_errors=True)

    # Ensure .pt is in local_dir (in case it was inside a zip in a subfolder)
    for pt in local_dir.rglob("bert_bilstm_crf_state.pt"):
        if pt.parent != local_dir:
            shutil.copy2(pt, local_dir / "bert_bilstm_crf_state.pt")
            break

    if not (local_dir / "ner_config.json").exists() or not (local_dir / "bert_bilstm_crf_state.pt").exists():
        print("Warning: ner_config.json or bert_bilstm_crf_state.pt not found in download. Check the Drive folder contents.")
    else:
        print("Download complete.")

    print(f"\nSet in .env:\n  RESUME_NER_LOAD_DIR={local_dir.resolve()}")
    print("Or relative from project root:\n  RESUME_NER_LOAD_DIR=./model/resume_ner")


if __name__ == "__main__":
    main()
