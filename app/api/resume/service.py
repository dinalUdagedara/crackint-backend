"""
Orchestrate text extraction (PDF) and NER for resume entity extraction.
"""

import asyncio
import logging
from typing import Dict, List

from fastapi import HTTPException

from app.ml.resume_ner import parse_resume_hybrid
from app.agents.resume_entity_agent import validate_and_correct_entities
from app.services.text_extraction import extract_text_from_file

logger = logging.getLogger(__name__)


def _run_ner_sync(text: str) -> Dict[str, List[str]]:
    """Run NER in thread pool so async route is not blocked."""
    return parse_resume_hybrid(text)


async def extract_entities_from_text(
    text: str,
    run_agent: bool = False,
) -> Dict[str, List[str]]:
    """
    Run hybrid NER on raw text. If run_agent is True and the agent is configured,
    validate and correct entities via the LLM. Safe to call from async route (NER runs in executor).
    """
    logger.info(
        "Resume extract: text input (len=%d), run_agent=%s",
        len(text),
        run_agent,
    )
    loop = asyncio.get_event_loop()
    entities = await loop.run_in_executor(None, _run_ner_sync, text)
    logger.info(
        "Resume extract: NER done (NAME=%d, SKILL=%d, etc.); run_agent=%s",
        len(entities.get("NAME", [])),
        len(entities.get("SKILL", [])),
        run_agent,
    )
    if run_agent:
        entities = await validate_and_correct_entities(text, entities)
    return entities


async def extract_entities_from_file_bytes(
    content: bytes,
    content_type: str,
    run_agent: bool = False,
) -> tuple[str, Dict[str, List[str]]]:
    """
    Extract text from file bytes (PDF or image via OCR), then run NER. If run_agent is True and the agent is configured,
    validate and correct entities via the LLM. Returns (raw_text, entities).
    """
    logger.info("Resume extract: file input (bytes=%d, content_type=%s), run_agent=%s", len(content), content_type, run_agent)
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        raw_text = extract_text_from_file(content, content_type)
    except ValueError as e:
        logger.warning("Resume extract: text extraction failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not raw_text.strip():
        logger.warning("Resume extract: file produced empty text")
        raise HTTPException(status_code=400, detail="No text could be extracted from the file")

    logger.info("Resume extract: text extracted (len=%d), running NER + agent=%s", len(raw_text), run_agent)
    entities = await extract_entities_from_text(raw_text, run_agent=run_agent)
    return raw_text, entities
