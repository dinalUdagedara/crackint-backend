"""
Resume upload, entity extraction, and update endpoints.
"""

import logging
import uuid as uuid_pkg

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    UploadFile,
)

logger = logging.getLogger(__name__)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.resume.schemas import (
    DeleteAllResumesResponse,
    ResumeEntitiesUpdate,
    ResumeExtractPreviewResponse,
    ResumeExtractResponse,
    ResumeListItem,
)
from app.api.resume import service as resume_service
from app.common.http_response_model import CommonResponse, PageMeta
from app.config import settings
from app.models import Resume, User
from app.services.text_extraction import SUPPORTED_FILE_CONTENT_TYPES

router = APIRouter()

MAX_BYTES = (settings.MAX_UPLOAD_SIZE_MB or 10) * 1024 * 1024
ALLOWED_CONTENT_TYPES = SUPPORTED_FILE_CONTENT_TYPES
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get(
    "",
    response_model=CommonResponse[list[ResumeListItem]],
    name="List all resumes",
    summary="List the current user's resumes with pagination.",
)
async def list_resumes(
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page."
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Returns a paginated list of resumes for the authenticated user.
    """
    # Count total for current user
    count_q = (
        select(func.count())
        .select_from(Resume)
        .where(Resume.user_id == current_user.id)
    )
    total_result = await session.execute(count_q)
    total_items = total_result.scalar_one() or 0
    total_pages = max(1, (total_items + page_size - 1) // page_size)

    # Fetch page
    offset = (page - 1) * page_size
    q = (
        select(Resume)
        .where(Resume.user_id == current_user.id)
        .order_by(Resume.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(q)
    resumes = list(result.scalars().all())

    payload = [ResumeListItem.model_validate(r) for r in resumes]
    meta = PageMeta(
        page=page, page_size=page_size, total_pages=total_pages, total_items=total_items
    )
    return CommonResponse(
        success=True,
        message="Resumes retrieved successfully",
        payload=payload,
        meta=meta,
    )


@router.get(
    "/{resume_id}",
    response_model=CommonResponse[ResumeListItem],
    name="Get resume by ID",
    summary="Get a single resume by ID.",
)
async def get_resume(
    resume_id: uuid_pkg.UUID = Path(..., description="Resume ID."),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Returns the resume record if found and owned by the current user; 404 otherwise."""
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return CommonResponse(
        success=True,
        message="Resume retrieved successfully",
        payload=ResumeListItem.model_validate(resume),
    )


@router.post(
    "/preview-extract",
    response_model=CommonResponse[ResumeExtractPreviewResponse],
    name="Preview extracted text and entities",
    summary="Return the text passed to the NER model and extracted entities (no DB save). Use to monitor PDF extraction and model input.",
)
async def preview_resume_extract(
    file: UploadFile | None = File(default=None, description="Resume PDF file"),
    text: str | None = Form(
        default=None, description="Raw resume text (use when not uploading a file)"
    ),
    validate: bool = Query(
        default=False,
        description="If true, run AI agent to validate and correct entities (requires RESUME_ENTITY_AGENT_ENABLED and OPENAI_API_KEY).",
    ),
):
    """
    Accept either **file** (PDF) or **text**. Returns:
    - **extracted_text**: The exact string passed to the NER model (from PDF or your text).
    - **entities**: Entities extracted by the model.

    Does **not** save to the database. Use this to debug or monitor what the model receives.
    """
    logger.info(
        "Resume preview-extract: validate=%s, has_file=%s, has_text=%s",
        validate,
        file is not None,
        text is not None and bool(text and text.strip()),
    )
    if file is not None and text is not None:
        logger.warning("Resume preview-extract: 400 - client sent both file and text")
        raise HTTPException(
            status_code=400, detail="Send either a file or text, not both."
        )
    if file is None and (text is None or not text.strip()):
        logger.warning("Resume preview-extract: 400 - neither file nor text provided")
        raise HTTPException(
            status_code=400,
            detail="Send either a file (PDF or image) or form field 'text' with resume content.",
        )

    if file is not None:
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Only PDF and images (PNG, JPEG, WebP) are accepted.",
            )
        content = await file.read()
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed ({settings.MAX_UPLOAD_SIZE_MB} MB).",
            )
        content_type = file.content_type or "application/octet-stream"
        raw_text, entities = await resume_service.extract_entities_from_file_bytes(
            content, content_type, run_agent=validate
        )
        payload = ResumeExtractPreviewResponse(
            extracted_text=raw_text, entities=entities
        )
        logger.info("Resume preview-extract: done (file, text_len=%d)", len(raw_text))
    else:
        text_clean = text.strip()
        entities = await resume_service.extract_entities_from_text(
            text_clean, run_agent=validate
        )
        payload = ResumeExtractPreviewResponse(
            extracted_text=text_clean, entities=entities
        )
        logger.info("Resume preview-extract: done (text, len=%d)", len(text_clean))

    return CommonResponse(
        success=True,
        message="Preview: text passed to model and extracted entities",
        payload=payload,
    )


@router.post(
    "/extract",
    response_model=CommonResponse[ResumeExtractResponse],
    name="Extract entities from resume",
    summary="Extract entities (NAME, EMAIL, SKILL, etc.) from resume PDF or raw text.",
)
async def extract_resume_entities(
    file: UploadFile | None = File(default=None, description="Resume PDF file"),
    text: str | None = Form(
        default=None, description="Raw resume text (use when not uploading a file)"
    ),
    validate: bool = Query(
        default=False,
        description="If true, run AI agent to validate and correct entities (requires RESUME_ENTITY_AGENT_ENABLED and OPENAI_API_KEY).",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Accept either:
    - **file**: PDF upload (multipart/form-data), or
    - **text**: Form field with raw resume text.

    Returns extracted entities: NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE.
    """
    logger.info(
        "Resume extract: validate=%s, has_file=%s, has_text=%s",
        validate,
        file is not None,
        text is not None and bool(text and text.strip()),
    )
    if file is not None and text is not None:
        logger.warning("Resume extract: 400 - client sent both file and text")
        raise HTTPException(
            status_code=400,
            detail="Send either a file or text, not both.",
        )
    if file is None and (text is None or not text.strip()):
        logger.warning("Resume extract: 400 - neither file nor text provided")
        raise HTTPException(
            status_code=400,
            detail="Send either a file (PDF or image) or form field 'text' with resume content.",
        )

    if file is not None:
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            logger.warning(
                "Resume extract: 400 - invalid content type %s", file.content_type
            )
            raise HTTPException(
                status_code=400,
                detail="Only PDF and images (PNG, JPEG, WebP) are accepted.",
            )
        content = await file.read()
        if len(content) > MAX_BYTES:
            logger.warning(
                "Resume extract: 400 - file too large (%d bytes)", len(content)
            )
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed ({settings.MAX_UPLOAD_SIZE_MB} MB).",
            )
        content_type = file.content_type or "application/octet-stream"
        raw_text, entities = await resume_service.extract_entities_from_file_bytes(
            content, content_type, run_agent=validate
        )
        payload = ResumeExtractResponse(entities=entities, raw_text=raw_text)
    else:
        text_clean = text.strip()
        entities = await resume_service.extract_entities_from_text(
            text_clean, run_agent=validate
        )
        payload = ResumeExtractResponse(entities=entities, raw_text=text_clean)

    resume = Resume(
        user_id=current_user.id,
        entities=payload.entities,
        raw_text=payload.raw_text,
    )
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    logger.info(
        "Resume extract: done (resume_id=%s, persisted), validate=%s",
        resume.id,
        validate,
    )

    return CommonResponse(
        success=True,
        message="Entities extracted successfully",
        payload=payload,
    )


@router.put(
    "/{resume_id}",
    response_model=CommonResponse[ResumeExtractResponse],
    name="Update resume",
    summary="Replace an existing resume with new PDF or text; re-extract entities and update the record.",
)
async def update_resume(
    resume_id: uuid_pkg.UUID = Path(..., description="Resume ID to update"),
    file: UploadFile | None = File(default=None, description="New resume PDF file"),
    text: str | None = Form(
        default=None, description="New raw resume text (use when not uploading a file)"
    ),
    validate: bool = Query(
        default=False,
        description="If true, run AI agent to validate and correct entities (requires RESUME_ENTITY_AGENT_ENABLED and OPENAI_API_KEY).",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Accept either **file** (PDF) or **text**. Re-runs extraction and updates the resume record.
    Returns the new extracted entities and raw_text. Use when the user confirms "Replace resume".
    """
    logger.info(
        "Resume update: resume_id=%s, validate=%s, has_file=%s, has_text=%s",
        resume_id,
        validate,
        file is not None,
        text is not None and bool(text and text.strip()),
    )
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

    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")

    if file is not None:
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Only PDF and images (PNG, JPEG, WebP) are accepted.",
            )
        content = await file.read()
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed ({settings.MAX_UPLOAD_SIZE_MB} MB).",
            )
        content_type = file.content_type or "application/octet-stream"
        raw_text, entities = await resume_service.extract_entities_from_file_bytes(
            content, content_type, run_agent=validate
        )
        resume.entities = entities
        resume.raw_text = raw_text
    else:
        text_clean = text.strip()
        entities = await resume_service.extract_entities_from_text(
            text_clean, run_agent=validate
        )
        resume.entities = entities
        resume.raw_text = text_clean

    await session.commit()
    await session.refresh(resume)

    payload = ResumeExtractResponse(entities=resume.entities, raw_text=resume.raw_text)
    return CommonResponse(
        success=True,
        message="Resume updated successfully",
        payload=payload,
    )


@router.patch(
    "/{resume_id}",
    response_model=CommonResponse[ResumeListItem],
    name="Update resume entities",
    summary="Update only the extracted entity fields you send; other fields stay unchanged.",
)
async def patch_resume_entities(
    resume_id: uuid_pkg.UUID = Path(..., description="Resume ID to update."),
    body: ResumeEntitiesUpdate = ...,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Send only the entity types you want to change. Each key must be one of:
    NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE.
    Values replace the existing list for that key; omitted keys are not modified.
    """
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")

    # Merge: only update keys present in body
    updated = dict(resume.entities)
    for key, values in body.entities.items():
        updated[key] = values
    resume.entities = updated

    await session.commit()
    await session.refresh(resume)

    return CommonResponse(
        success=True,
        message="Resume entities updated successfully",
        payload=ResumeListItem.model_validate(resume),
    )


@router.delete(
    "",
    response_model=CommonResponse[DeleteAllResumesResponse],
    name="Delete all resumes",
    summary="Delete all of the current user's resume records.",
)
async def delete_all_resumes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Deletes every resume belonging to the current user. Returns the number deleted.
    """
    count_result = await session.execute(
        select(func.count())
        .select_from(Resume)
        .where(Resume.user_id == current_user.id)
    )
    deleted_count = count_result.scalar_one() or 0
    await session.execute(delete(Resume).where(Resume.user_id == current_user.id))
    await session.commit()
    return CommonResponse(
        success=True,
        message=f"Deleted {deleted_count} resume(s).",
        payload=DeleteAllResumesResponse(deleted_count=deleted_count),
    )
