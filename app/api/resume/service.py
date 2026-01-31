"""
Orchestrate text extraction (PDF) and NER for resume entity extraction.
"""

import asyncio
from typing import Dict, List

from fastapi import HTTPException

from app.ml.resume_ner import parse_resume_hybrid
from app.services.text_extraction import extract_text_from_pdf


def _run_ner_sync(text: str) -> Dict[str, List[str]]:
    """Run NER in thread pool so async route is not blocked."""
    return parse_resume_hybrid(text)


async def extract_entities_from_text(text: str) -> Dict[str, List[str]]:
    """
    Run hybrid NER on raw text. Safe to call from async route (runs in executor).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_ner_sync, text)


async def extract_entities_from_pdf_bytes(content: bytes) -> tuple[str, Dict[str, List[str]]]:
    """
    Extract text from PDF bytes, then run NER. Returns (raw_text, entities).
    """
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        raw_text = extract_text_from_pdf(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the PDF")

    entities = await extract_entities_from_text(raw_text)
    return raw_text, entities
