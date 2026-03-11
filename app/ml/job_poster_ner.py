"""
Job poster NER: load BERT-BiLSTM-CRF from JOB_POSTER_NER_LOAD_DIR and run extraction.
Entity types: JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from transformers import BertModel, BertTokenizer

from app.config import settings

# Rule-based SALARY extraction (high recall; merged with model output in hybrid)
SALARY_RE = re.compile(
    r"\$[\d,]+\.?\d*\s*(k|K|M)?\s*(-|–|to)\s*\$?[\d,]+\.?\d*\s*(k|K|M)?"
    r"|\$[\d,]+\.?\d*\s*(k|K|M)?"
    r"|£[\d,]+\.?\d*\s*(k|K)?"
    r"|\d+\s*(k|K)\s*-\s*\d+\s*(k|K)"
    r"|Competitive|competitive"
)

# Model, tokenizer, device, and label mapping (set by load_model)
_tokenizer: Any = None
_model: Any = None
_device: Any = None
_id2label: Optional[Dict[int, str]] = None
_num_labels: int = 0


class BertBiLSTMCRF(torch.nn.Module):
    """BERT + BiLSTM + CRF for NER. Same architecture as resume NER; num_labels matches job poster config."""

    def __init__(
        self,
        bert_name: str = "bert-base-uncased",
        hidden_dim: int = 256,
        num_labels: int = 17,
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
    Load tokenizer and model from JOB_POSTER_NER_LOAD_DIR.
    Call once at startup or lazily on first request.
    """
    global _tokenizer, _model, _device, _id2label, _num_labels

    load_dir = getattr(settings, "JOB_POSTER_NER_LOAD_DIR", None)
    if not load_dir or not Path(load_dir).exists():
        _tokenizer = _model = _device = _id2label = None
        _num_labels = 0
        print("Job poster NER: no load dir or path missing; /jobs/extract will return empty entities.")
        return

    config_path = Path(load_dir) / "ner_config.json"
    state_path = Path(load_dir) / "bert_bilstm_crf_state.pt"
    if not config_path.exists() or not state_path.exists():
        _tokenizer = _model = _device = _id2label = None
        _num_labels = 0
        print("Job poster NER: config or state file missing; /jobs/extract will return empty entities.")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        load_config = json.load(f)

    tags: List[str] = load_config["tags"]
    bert_name: str = load_config.get("bert_name", "bert-base-uncased")
    num_labels: int = load_config["num_labels"]
    hidden_dim: int = load_config.get("hidden_dim", 256)

    _id2label = {i: t for i, t in enumerate(tags)}
    _num_labels = num_labels

    if torch.cuda.is_available():
        _device = torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        _device = torch.device("mps")
    else:
        _device = torch.device("cpu")

    _tokenizer = BertTokenizer.from_pretrained(load_dir)
    _model = BertBiLSTMCRF(
        bert_name=bert_name,
        hidden_dim=hidden_dim,
        num_labels=num_labels,
    ).to(_device)
    _model.load_state_dict(torch.load(state_path, map_location=_device))
    _model.eval()
    print(f"Job poster NER: loaded from {load_dir} (num_labels={num_labels})")


def _clean_entity(s: str) -> str:
    """Strip leading/trailing punctuation and whitespace from extracted entity text."""
    if not s:
        return s
    s = s.strip()
    while s and s[-1] in ",.;:!?)]}\"'":
        s = s[:-1].rstrip()
    while s and s[0] in "([{\"'":
        s = s[1:].lstrip()
    return s


def _parse_job_poster(
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

    # Build entity dict: handle B-X and leading I-X; clean and dedupe
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
            raw = " ".join(phrase)
            cleaned = _clean_entity(raw)
            if cleaned:
                entities.setdefault(entity_type, []).append(cleaned)
        elif tag.startswith("I-"):
            entity_type = tag[2:]
            if prev_tag not in (f"B-{entity_type}", f"I-{entity_type}"):
                phrase = [words[i]]
                i += 1
                while i < len(words) and i < len(pred_tags) and pred_tags[i] == f"I-{entity_type}":
                    phrase.append(words[i])
                    i += 1
                raw = " ".join(phrase)
                cleaned = _clean_entity(raw)
                if cleaned:
                    entities.setdefault(entity_type, []).append(cleaned)
            else:
                i += 1
        else:
            i += 1
    for k in entities:
        entities[k] = list(dict.fromkeys(entities[k]))
    return words, pred_tags, entities


def _extract_salary_rules(text: str) -> List[str]:
    """Extract salary-like spans from text using regex. Deduplicated."""
    return list(dict.fromkeys(m.group(0).strip() for m in SALARY_RE.finditer(text)))


def parse_job_poster_hybrid(text: str) -> Dict[str, List[str]]:
    """
    Extract entities from job poster text using the job poster NER model.
    Returns only entity types that have at least one value (trained or rule-based).
    E.g. with current SkillSpan-trained model: SKILLS_REQUIRED and SALARY only.
    When model is not loaded, returns empty dict.
    """
    text = text.strip()
    if not text:
        return {}

    if not is_model_loaded():
        return {}

    _, _, entities = _parse_job_poster(text)
    base = _empty_entities()
    for k in base:
        base[k] = entities.get(k, [])
    sal = _extract_salary_rules(text)
    if sal:
        base["SALARY"] = list(dict.fromkeys((base["SALARY"] or []) + sal))
    normalized = _normalize_entities(base)
    return {k: v for k, v in normalized.items() if v}


def _normalize_entities(entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Strip punctuation from phrases, dedupe (case-insensitive), preserve order."""
    result = _empty_entities()
    for k, vals in entities.items():
        if k not in result:
            result[k] = []
        seen: set[tuple[str, str]] = set()
        out: List[str] = []
        for v in vals:
            v = _clean_entity(v)
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
        "JOB_TITLE": [],
        "COMPANY": [],
        "LOCATION": [],
        "SALARY": [],
        "SKILLS_REQUIRED": [],
        "EXPERIENCE_REQUIRED": [],
        "EDUCATION_REQUIRED": [],
        "JOB_TYPE": [],
    }


def is_model_loaded() -> bool:
    return _model is not None and _tokenizer is not None
