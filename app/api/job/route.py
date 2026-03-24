"""
Job description upload and entity extraction endpoint.
"""

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.common.http_response_model import CommonResponse
from app.api.job.schemas import JobExtractResponse
from app.api.job import service as job_service
from app.config import settings
from app.services.text_extraction import UNSUPPORTED_UPLOAD_DETAIL, upload_content_type_allowed

router = APIRouter()

MAX_BYTES = (settings.MAX_UPLOAD_SIZE_MB or 10) * 1024 * 1024


@router.post(
    "/extract",
    response_model=CommonResponse[JobExtractResponse],
    name="Extract entities from job description",
    summary="Extract entities from job description PDF or raw text (job poster NER; empty when model not loaded).",
)
async def extract_job_entities(
    file: UploadFile | None = File(default=None, description="Job description PDF file"),
    text: str | None = Form(default=None, description="Raw job description text (use when not uploading a file)"),
    validate: bool = Query(default=False, description="If true, run AI agent to validate and correct entities (requires JOB_ENTITY_AGENT_ENABLED and OPENAI_API_KEY)."),
):
    """
    Accept either:
    - **file**: PDF or image (PNG, JPEG, WebP) upload (multipart/form-data), or
    - **text**: Form field with raw job description text.

    Returns extracted entities when job poster NER is loaded: JOB_TITLE, COMPANY, LOCATION,
    SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE.
    When the model is not loaded, returns empty entities.
    
    If **validate** is true and JOB_ENTITY_AGENT_ENABLED is set, an AI agent will validate and correct the entities.
    """
    if file is not None and text is not None:
        raise HTTPException(
            status_code=400,
            detail="Send either a file or text, not both.",
        )
    if file is None and (text is None or not text.strip()):
        raise HTTPException(
            status_code=400,
            detail="Send either a file (PDF, image, or .docx) or form field 'text' with job description content.",
        )

    if file is not None:
        if file.content_type and not upload_content_type_allowed(
            file.content_type, file.filename
        ):
            raise HTTPException(
                status_code=400,
                detail=UNSUPPORTED_UPLOAD_DETAIL,
            )
        content = await file.read()
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed ({settings.MAX_UPLOAD_SIZE_MB} MB).",
            )
        content_type = file.content_type or "application/octet-stream"
        raw_text, entities = await job_service.extract_entities_from_file_bytes(
            content, content_type, run_agent=validate, filename=file.filename
        )
        payload = JobExtractResponse(entities=entities, raw_text=raw_text)
    else:
        text_clean = text.strip()
        entities = await job_service.extract_entities_from_text(text_clean, run_agent=validate)
        payload = JobExtractResponse(entities=entities, raw_text=None)

    return CommonResponse(
        success=True,
        message="Job description entities extracted successfully",
        payload=payload,
    )
