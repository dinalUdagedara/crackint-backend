"""
Resume upload and entity extraction endpoint.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.common.http_response_model import CommonResponse
from app.api.resume.schemas import ResumeExtractResponse
from app.api.resume import service as resume_service
from app.config import settings

router = APIRouter()

MAX_BYTES = (settings.MAX_UPLOAD_SIZE_MB or 10) * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf"}


@router.post(
    "/extract",
    response_model=CommonResponse[ResumeExtractResponse],
    name="Extract entities from resume",
    summary="Extract entities (NAME, EMAIL, SKILL, etc.) from resume PDF or raw text.",
)
async def extract_resume_entities(
    file: UploadFile | None = File(default=None, description="Resume PDF file"),
    text: str | None = Form(default=None, description="Raw resume text (use when not uploading a file)"),
):
    """
    Accept either:
    - **file**: PDF upload (multipart/form-data), or
    - **text**: Form field with raw resume text.

    Returns extracted entities: NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE.
    """
    if file is not None and text is not None:
        raise HTTPException(
            status_code=400,
            detail="Send either a file or text, not both.",
        )
    if file is None and (text is None or not text.strip()):
        raise HTTPException(
            status_code=400,
            detail="Send either a file (PDF) or form field 'text' with resume content.",
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
        raw_text, entities = await resume_service.extract_entities_from_pdf_bytes(content)
        payload = ResumeExtractResponse(entities=entities, raw_text=raw_text)
    else:
        text_clean = text.strip()
        entities = await resume_service.extract_entities_from_text(text_clean)
        payload = ResumeExtractResponse(entities=entities, raw_text=None)

    return CommonResponse(
        success=True,
        message="Entities extracted successfully",
        payload=payload,
    )
