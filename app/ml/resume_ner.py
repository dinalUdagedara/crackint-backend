"""
Resume NER: load BERT-BiLSTM-CRF from RESUME_NER_LOAD_DIR and run hybrid extraction.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from transformers import BertModel, BertTokenizer

from app.config import settings

# Model, tokenizer, device, and label mapping (set by load_model)
_tokenizer: Any = None
_model: Any = None
_device: Any = None
_id2label: Optional[Dict[int, str]] = None
_num_labels: int = 0


class BertBiLSTMCRF(torch.nn.Module):
    """BERT + BiLSTM + CRF for NER. Must match the notebook architecture."""

    def __init__(
        self,
        bert_name: str = "bert-base-uncased",
        hidden_dim: int = 256,
        num_labels: int = 13,
        dropout: float = 0.3,
    ):
        super().__init__()
        from torchcrf import CRF

        self.bert = BertModel.from_pretrained(bert_name)
        self.lstm = torch.nn.LSTM(
            self.bert.config.hidden_size,
            hidden_dim // 2,
            num_layers=1,
            bidirectional=True,
            batch_first=True,
        )
        self.drop = torch.nn.Dropout(dropout)
        self.fc = torch.nn.Linear(hidden_dim, num_labels)
        self.crf = CRF(num_labels, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: Optional[torch.Tensor] = None,
    ):
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        out, _ = self.lstm(self.drop(out))
        emissions = self.fc(self.drop(out))
        mask_b = attention_mask.bool()
        if labels is not None:
            labels = labels.clone().masked_fill(labels == -100, 0)
            return -self.crf(emissions, labels, mask=mask_b, reduction="mean")
        return self.crf.decode(emissions, mask=mask_b)


def load_model() -> None:
    """
    Load tokenizer and model from RESUME_NER_LOAD_DIR.
    Call once at startup or lazily on first request.
    """
    global _tokenizer, _model, _device, _id2label, _num_labels

    load_dir = getattr(settings, "RESUME_NER_LOAD_DIR", None)
    if not load_dir or not Path(load_dir).exists():
        _tokenizer = _model = _device = _id2label = None
        _num_labels = 0
        return

    config_path = Path(load_dir) / "ner_config.json"
    state_path = Path(load_dir) / "bert_bilstm_crf_state.pt"
    if not config_path.exists() or not state_path.exists():
        _tokenizer = _model = _device = _id2label = None
        _num_labels = 0
        return

    with open(config_path, "r", encoding="utf-8") as f:
        load_config = json.load(f)

    tags: List[str] = load_config["tags"]
    bert_name: str = load_config.get("bert_name", "bert-base-uncased")
    num_labels: int = load_config["num_labels"]

    _id2label = {i: t for i, t in enumerate(tags)}
    _num_labels = num_labels

    if torch.cuda.is_available():
        _device = torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        _device = torch.device("mps")
    else:
        _device = torch.device("cpu")

    _tokenizer = BertTokenizer.from_pretrained(load_dir)
    _model = BertBiLSTMCRF(bert_name=bert_name, num_labels=num_labels).to(_device)
    _model.load_state_dict(torch.load(state_path, map_location=_device))
    _model.eval()


def _parse_resume(
    text: str,
    max_len: int = 512,
) -> Tuple[List[str], List[str], Dict[str, List[str]]]:
    """Tokenize text, run NER, return (words, pred_tags, entities). Handles B- and leading I- spans."""
    if _tokenizer is None or _model is None or _id2label is None:
        return [], [], _empty_entities()

    words = re.findall(r"\S+", text)
    if not words:
        return [], [], _empty_entities()

    first_idx: List[int] = []
    toks: List[str] = ["[CLS]"]
    for w in words:
        sub = _tokenizer.tokenize(w) or [_tokenizer.unk_token]
        first_idx.append(len(toks))
        toks.extend(sub)
    toks.append("[SEP]")
    ids = _tokenizer.convert_tokens_to_ids(toks)
    if len(ids) > max_len:
        ids = ids[: max_len - 1] + [_tokenizer.sep_token_id]
        first_idx = [i for i in first_idx if i < len(ids)]
        words = words[: len(first_idx)]
    mask = [1] * len(ids)
    inp = torch.tensor([ids], dtype=torch.long).to(_device)
    mask_t = torch.tensor([mask], dtype=torch.long).to(_device)
    _model.eval()
    with torch.no_grad():
        preds = _model(inp, mask_t)
    pred_tags = [_id2label.get(preds[0][i], "O") for i in first_idx]

    # Build entity dict: handle B-X and leading I-X (when model misses B-)
    entities: Dict[str, List[str]] = {}
    i = 0
    while i < len(words):
        tag = pred_tags[i] if i < len(pred_tags) else "O"
        prev_tag = pred_tags[i - 1] if i > 0 and i - 1 < len(pred_tags) else "O"
        if tag.startswith("B-"):
            entity_type = tag[2:]
            phrase = [words[i]]
            i += 1
            while i < len(words) and i < len(pred_tags) and pred_tags[i] == f"I-{entity_type}":
                phrase.append(words[i])
                i += 1
            entities.setdefault(entity_type, []).append(" ".join(phrase))
        elif tag.startswith("I-"):
            entity_type = tag[2:]
            if prev_tag not in (f"B-{entity_type}", f"I-{entity_type}"):
                phrase = [words[i]]
                i += 1
                while i < len(words) and i < len(pred_tags) and pred_tags[i] == f"I-{entity_type}":
                    phrase.append(words[i])
                    i += 1
                entities.setdefault(entity_type, []).append(" ".join(phrase))
            else:
                i += 1
        else:
            i += 1
    return words, pred_tags, entities


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)


def _extract_email_rules(text: str) -> List[str]:
    return list(dict.fromkeys(EMAIL_RE.findall(text)))


def _extract_name_heuristic(text: str) -> List[str]:
    lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
    for line in lines[:4]:
        if "@" in line or "http" in line.lower() or "www." in line.lower():
            continue
        parts = line.split()
        if 1 <= len(parts) <= 4 and all(
            p[0].isupper() for p in parts if len(p) > 0 and p[0].isalpha()
        ):
            c = " ".join(parts)
            if len(c) < 80 and not c.endswith("."):
                return [c]
    return []


def parse_resume_hybrid(text: str) -> Dict[str, List[str]]:
    """
    Extract entities from resume text: rules for NAME/EMAIL, model for SKILL, EXPERIENCE, EDUCATION, OCCUPATION.
    Returns a dict with keys NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE (lists of strings).
    """
    text = text.strip()
    if not text:
        return _empty_entities()

    if not is_model_loaded():
        return _normalize_entities(_stub_entities(text))

    rn = _extract_name_heuristic(text)
    re_list = _extract_email_rules(text)
    _, _, entities = _parse_resume(text)
    if rn:
        entities["NAME"] = rn
    if re_list:
        entities["EMAIL"] = re_list

    base = _empty_entities()
    for k in base:
        base[k] = entities.get(k, [])
    return _normalize_entities(base)


def _normalize_entities(entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Strip trailing punctuation from phrases, dedupe, preserve order."""
    result = _empty_entities()
    for k, vals in entities.items():
        seen = set()
        out = []
        for v in vals:
            v = v.rstrip(".,;:!?)\"'").strip()
            if not v:
                continue
            key = (k, v.lower())
            if key not in seen:
                seen.add(key)
                out.append(v)
        result[k] = out
    return result


def _empty_entities() -> Dict[str, List[str]]:
    return {
        "NAME": [],
        "EMAIL": [],
        "SKILL": [],
        "OCCUPATION": [],
        "EDUCATION": [],
        "EXPERIENCE": [],
    }


def _stub_entities(text: str) -> Dict[str, List[str]]:
    """Fallback when model is not loaded."""
    entities = _empty_entities()
    segments = re.split(r"\s{2,}|\n", text.strip(), maxsplit=1)
    name_candidate = (segments[0].strip() if segments else "").strip()
    if not name_candidate:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        name_candidate = lines[0] if lines else ""
    if name_candidate:
        entities["NAME"] = [name_candidate[:120].strip()] if len(name_candidate) > 120 else [name_candidate]
    for word in text.split():
        if "@" in word and "." in word:
            entities["EMAIL"].append(word)
            break
    return entities


def is_model_loaded() -> bool:
    return _model is not None and _tokenizer is not None
