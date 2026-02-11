"""
Orchestrate text extraction (PDF) and NER for job description entity extraction.
Uses job poster NER when JOB_POSTER_NER_LOAD_DIR is set; otherwise returns empty entities.
"""

import asyncio
from typing import Dict, List

from fastapi import HTTPException

from app.ml.job_poster_ner import is_model_loaded as job_poster_model_loaded
from app.ml.job_poster_ner import parse_job_poster_hybrid
from app.services.text_extraction import extract_text_from_file


def _run_ner_sync(text: str) -> Dict[str, List[str]]:
    """Run job poster NER in thread pool when loaded; otherwise return empty dict."""
    if job_poster_model_loaded():
        return parse_job_poster_hybrid(text)
    return {}


async def extract_entities_from_text(text: str) -> Dict[str, List[str]]:
    """
    Run hybrid NER on raw job description text. Safe to call from async route (runs in executor).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_ner_sync, text)


async def extract_entities_from_file_bytes(
    content: bytes,
    content_type: str,
) -> tuple[str, Dict[str, List[str]]]:
    """
    Extract text from job description file bytes (PDF or image via OCR), then run NER. Returns (raw_text, entities).
    """
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        raw_text = extract_text_from_file(content, content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from the file",
        )

    entities = await extract_entities_from_text(raw_text)
    return raw_text, entities
