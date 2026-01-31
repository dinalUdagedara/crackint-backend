"""
Resume NER integration point.

Refactor your notebook's load_model() and parse_resume_hybrid() here.
Set RESUME_NER_LOAD_DIR to the directory where the saved model, tokenizer, and config live.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

# Placeholder: replace with your actual model/tokenizer types after refactoring from notebook
_tokenizer: Any = None
_model: Any = None
_device: Any = None
_id2label: Optional[Dict[int, str]] = None
_label2id: Optional[Dict[str, int]] = None


def load_model() -> None:
    """
    Load tokenizer and model from RESUME_NER_LOAD_DIR.
    Call once at startup or lazily on first request.
    """
    global _tokenizer, _model, _device, _id2label, _label2id

    load_dir = getattr(settings, "RESUME_NER_LOAD_DIR", None)
    if not load_dir or not Path(load_dir).exists():
        # Stub: no model path configured; keep placeholders None
        _tokenizer = _model = _device = _id2label = _label2id = None
        return

    # TODO: Refactor from notebook:
    # - Load tokenizer from load_dir (e.g. AutoTokenizer.from_pretrained(load_dir))
    # - Load model state from load_dir (your BERT+BiLSTM+CRF checkpoint)
    # - Load config (tags / id2label) from load_dir
    # - Set device (cuda if available else cpu)
    # _tokenizer = ...
    # _model = ...
    # _device = ...
    # _id2label = ...
    # _label2id = ...
    pass


def parse_resume_hybrid(text: str) -> Dict[str, List[str]]:
    """
    Extract entities from resume text using hybrid approach:
    rules for NAME/EMAIL, model for SKILL, EXPERIENCE, EDUCATION, OCCUPATION.

    Args:
        text: Raw resume text (from PDF or paste).

    Returns:
        Entity dict: keys are entity types (NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE),
        values are lists of extracted phrases.
    """
    if not text or not text.strip():
        return _empty_entities()

    # Stub: when model is not loaded, return placeholder structure
    if _model is None or _tokenizer is None:
        return _stub_entities(text)

    # TODO: Refactor from notebook:
    # 1. Rule-based: extract NAME (e.g. first title-case line), EMAIL (regex)
    # 2. Model: tokenize text, run model, decode BIO tags to spans
    # 3. Merge into single dict: { "NAME": [...], "EMAIL": [...], "SKILL": [...], ... }
    # return _run_hybrid(text, _tokenizer, _model, _device, _id2label)
    return _stub_entities(text)


def _empty_entities() -> Dict[str, List[str]]:
    """Return empty entity dict with all expected keys."""
    return {
        "NAME": [],
        "EMAIL": [],
        "SKILL": [],
        "OCCUPATION": [],
        "EDUCATION": [],
        "EXPERIENCE": [],
    }


def _stub_entities(text: str) -> Dict[str, List[str]]:
    """Placeholder entities until notebook code is refactored."""
    import re

    entities = _empty_entities()
    # NAME: first segment (split by 2+ spaces or newline) or first line, capped at 120 chars
    segments = re.split(r"\s{2,}|\n", text.strip(), maxsplit=1)
    name_candidate = (segments[0].strip() if segments else "").strip()
    if not name_candidate:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        name_candidate = lines[0] if lines else ""
    if name_candidate:
        entities["NAME"] = [name_candidate[:120].strip()] if len(name_candidate) > 120 else [name_candidate]
    # EMAIL: any token containing @ and .
    for word in text.split():
        if "@" in word and "." in word:
            entities["EMAIL"].append(word)
            break
    return entities


def is_model_loaded() -> bool:
    """Return True if NER model has been loaded (for health/readiness checks)."""
    return _model is not None and _tokenizer is not None
