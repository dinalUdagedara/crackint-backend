"""
Job description upload and entity extraction endpoint.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.common.http_response_model import CommonResponse
from app.api.job.schemas import JobExtractResponse
from app.api.job import service as job_service
from app.config import settings

router = APIRouter()

MAX_BYTES = (settings.MAX_UPLOAD_SIZE_MB or 10) * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf"}


@router.post(
    "/extract",
    response_model=CommonResponse[JobExtractResponse],
    name="Extract entities from job description",
    summary="Extract entities from job description PDF or raw text (job poster NER or resume NER fallback).",
)
async def extract_job_entities(
    file: UploadFile | None = File(default=None, description="Job description PDF file"),
    text: str | None = Form(default=None, description="Raw job description text (use when not uploading a file)"),
):
    """
    Accept either:
    - **file**: PDF upload (multipart/form-data), or
    - **text**: Form field with raw job description text.

    Returns extracted entities. When job poster NER is loaded: JOB_TITLE, COMPANY, LOCATION,
    SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE.
    Otherwise (fallback): SKILL, OCCUPATION, EDUCATION, EXPERIENCE.
    """
    if file is not None and text is not None:
        raise HTTPException(
            status_code=400,
            detail="Send either a file or text, not both.",
        )
    if file is None and (text is None or not text.strip()):
        raise HTTPException(
            status_code=400,
            detail="Send either a file (PDF) or form field 'text' with job description content.",
        )

    if file is not None:
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are accepted. Use content-type application/pdf.",
            )
        content = await file.read()
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed ({settings.MAX_UPLOAD_SIZE_MB} MB).",
            )
        raw_text, entities = await job_service.extract_entities_from_pdf_bytes(content)
        payload = JobExtractResponse(entities=entities, raw_text=raw_text)
    else:
        text_clean = text.strip()
        entities = await job_service.extract_entities_from_text(text_clean)
        payload = JobExtractResponse(entities=entities, raw_text=None)

    return CommonResponse(
        success=True,
        message="Job description entities extracted successfully",
        payload=payload,
    )
