"""
Orchestrate text extraction (PDF) and NER for job description entity extraction.
Uses job poster NER when JOB_POSTER_NER_LOAD_DIR is set; otherwise returns empty entities.
"""

import asyncio
import logging
from typing import Dict, List

from fastapi import HTTPException

from app.ml.job_poster_ner import is_model_loaded as job_poster_model_loaded
from app.ml.job_poster_ner import parse_job_poster_hybrid
from app.agents.job_entity_agent import validate_and_correct_entities
from app.services.text_extraction import extract_text_from_file

logger = logging.getLogger(__name__)


def _run_ner_sync(text: str) -> Dict[str, List[str]]:
    """Run job poster NER in thread pool when loaded; otherwise return empty dict."""
    if job_poster_model_loaded():
        return parse_job_poster_hybrid(text)
    return {}


async def extract_entities_from_text(
    text: str,
    run_agent: bool = False,
) -> Dict[str, List[str]]:
    """
    Run hybrid NER on raw job description text. If run_agent is True and the agent is configured,
    validate and correct entities via the LLM. Safe to call from async route (NER runs in executor).
    """
    logger.info(
        "Job extract: text input (len=%d), run_agent=%s",
        len(text),
        run_agent,
    )
    loop = asyncio.get_event_loop()
    entities = await loop.run_in_executor(None, _run_ner_sync, text)
    logger.info(
        "Job extract: NER done (JOB_TITLE=%d, SKILLS_REQUIRED=%d, etc.); run_agent=%s",
        len(entities.get("JOB_TITLE", [])),
        len(entities.get("SKILLS_REQUIRED", [])),
        run_agent,
    )
    if run_agent:
        entities = await validate_and_correct_entities(text, entities)
    return entities


async def extract_entities_from_file_bytes(
    content: bytes,
    content_type: str,
    run_agent: bool = False,
    filename: str | None = None,
) -> tuple[str, Dict[str, List[str]]]:
    """
    Extract text from job description file bytes (PDF, image via OCR, or .docx), then run NER.
    If run_agent is True and the agent is configured, validate and correct entities via the LLM.
    Returns (raw_text, entities).
    """
    logger.info(
        "Job extract: file input (bytes=%d, content_type=%s, filename=%s), run_agent=%s",
        len(content),
        content_type,
        filename,
        run_agent,
    )
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        raw_text = extract_text_from_file(content, content_type, filename)
    except ValueError as e:
        logger.warning("Job extract: text extraction failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not raw_text.strip():
        logger.warning("Job extract: file produced empty text")
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from the file",
        )

    logger.info(
        "Job extract: text extracted (len=%d), running NER + agent=%s",
        len(raw_text),
        run_agent,
    )
    entities = await extract_entities_from_text(raw_text, run_agent=run_agent)
    return raw_text, entities
