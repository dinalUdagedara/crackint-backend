"""
Resume upload, entity extraction, and update endpoints.
"""

import logging
import uuid as uuid_pkg
from datetime import datetime
from typing import Optional

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
    DeleteResumeResponse,
    ResumeEntitiesUpdate,
    ResumeExtractPreviewResponse,
    ResumeExtractResponse,
    ResumeListItem,
    ResumeScoreResponse,
)
from app.api.resume import service as resume_service
from app.common.http_response_model import CommonResponse, PageMeta
from app.config import settings
from app.models import Resume, User
from app.services.cv_scoring import score_cv_from_file, score_cv_from_raw_text
from app.services.s3_uploads import try_upload_document_to_s3
from app.services.text_extraction import UNSUPPORTED_UPLOAD_DETAIL, upload_content_type_allowed

router = APIRouter()

MAX_BYTES = (settings.MAX_UPLOAD_SIZE_MB or 10) * 1024 * 1024
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


def _save_cv_score_to_resume(
    resume: Resume,
    score: float,
    breakdown: dict,
    suggestions: list,
    scored_at,
    session: AsyncSession,
) -> None:
    """Update resume with latest CV score and commit."""
    resume.cv_score = score
    resume.cv_breakdown = breakdown
    resume.cv_suggestions = suggestions
    resume.cv_scored_at = scored_at
    session.add(resume)


@router.post(
    "/score",
    response_model=CommonResponse[ResumeScoreResponse],
    name="Score CV from file",
    summary="Score a CV from PDF, image (vision), or Word (.docx) as text.",
)
async def post_resume_score(
    file: UploadFile = File(
        ..., description="Resume PDF, image (PNG, JPEG, WebP), or Word (.docx)"
    ),
    resume_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="If provided, save the score to this resume (must be owned by you).",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Upload a CV file. PDF and images are analyzed with the vision model; .docx files
    are converted to text and scored with the text model. Returns score (0-100), breakdown, and suggestions.
    If resume_id is provided, the score is saved to that resume for future use.
    Requires CV_SCORING_ENABLED=true and OPENAI_API_KEY.
    """
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
    try:
        result = await score_cv_from_file(content, content_type, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    scored_at = datetime.now()
    payload = ResumeScoreResponse(
        score=result.score,
        breakdown=result.breakdown,
        suggestions=result.suggestions,
        scored_at=scored_at,
    )

    if resume_id is not None:
        resume = await session.get(Resume, resume_id)
        if resume is None or resume.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Resume not found.")
        _save_cv_score_to_resume(
            resume,
            result.score,
            result.breakdown,
            result.suggestions,
            scored_at,
            session,
        )
        await session.commit()

    return CommonResponse(
        success=True,
        message="CV scored successfully",
        payload=payload,
    )


@router.get(
    "/{resume_id}/score",
    response_model=CommonResponse[ResumeScoreResponse],
    name="Score resume by ID",
    summary="Return stored CV score or run LLM and save. Uses stored raw_text when running LLM.",
)
async def get_resume_score(
    resume_id: uuid_pkg.UUID = Path(..., description="Resume ID."),
    force: bool = Query(
        False,
        description="If true, re-run the LLM to re-score and overwrite the stored score.",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Returns the latest CV score for this resume. If a score is already stored and
    force is false, it is returned without calling the LLM. Otherwise (no score, or
    force=true) the LLM is run (using stored raw_text), the result is saved to the
    resume, and returned.
    """
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")

    if (
        not force
        and resume.cv_score is not None
        and resume.cv_scored_at is not None
    ):
        payload = ResumeScoreResponse(
            score=resume.cv_score,
            breakdown=resume.cv_breakdown or {},
            suggestions=resume.cv_suggestions or [],
            scored_at=resume.cv_scored_at,
        )
        return CommonResponse(
            success=True,
            message="CV score retrieved (cached)",
            payload=payload,
        )

    if not (resume.raw_text or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Resume has no text to analyze. Use POST /score with file upload instead.",
        )
    text_len = len((resume.raw_text or "").strip())
    logger.info("CV score: resume_id=%s, raw_text_len=%d, running LLM", resume_id, text_len)
    try:
        result = await score_cv_from_raw_text(resume.raw_text)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    scored_at = datetime.now()
    _save_cv_score_to_resume(
        resume,
        result.score,
        result.breakdown,
        result.suggestions,
        scored_at,
        session,
    )
    await session.commit()

    payload = ResumeScoreResponse(
        score=result.score,
        breakdown=result.breakdown,
        suggestions=result.suggestions,
        scored_at=scored_at,
    )
    return CommonResponse(
        success=True,
        message="CV scored successfully",
        payload=payload,
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
            detail="Send either a file (PDF, image, or .docx) or form field 'text' with resume content.",
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
        raw_text, entities = await resume_service.extract_entities_from_file_bytes(
            content, content_type, run_agent=validate, filename=file.filename
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
            detail="Send either a file (PDF, image, or .docx) or form field 'text' with resume content.",
        )

    if file is not None:
        if file.content_type and not upload_content_type_allowed(
            file.content_type, file.filename
        ):
            logger.warning(
                "Resume extract: 400 - invalid content type %s", file.content_type
            )
            raise HTTPException(
                status_code=400,
                detail=UNSUPPORTED_UPLOAD_DETAIL,
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
        source_url = try_upload_document_to_s3(
            content, file.content_type, file.filename, "uploads/resumes"
        )
        raw_text, entities = await resume_service.extract_entities_from_file_bytes(
            content, content_type, run_agent=validate, filename=file.filename
        )
        resume = Resume(
            user_id=current_user.id,
            entities=entities,
            raw_text=raw_text,
            source_file_url=source_url,
        )
    else:
        text_clean = text.strip()
        entities = await resume_service.extract_entities_from_text(
            text_clean, run_agent=validate
        )
        resume = Resume(
            user_id=current_user.id,
            entities=entities,
            raw_text=text_clean,
            source_file_url=None,
        )

    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    logger.info(
        "Resume extract: done (resume_id=%s, persisted), validate=%s",
        resume.id,
        validate,
    )

    payload = ResumeExtractResponse(
        entities=resume.entities,
        raw_text=resume.raw_text,
        resume_id=resume.id,
        source_file_url=resume.source_file_url,
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
            detail="Send either a file (PDF, image, or .docx) or form field 'text' with resume content.",
        )

    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")

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
        source_url = try_upload_document_to_s3(
            content, file.content_type, file.filename, "uploads/resumes"
        )
        raw_text, entities = await resume_service.extract_entities_from_file_bytes(
            content, content_type, run_agent=validate, filename=file.filename
        )
        resume.entities = entities
        resume.raw_text = raw_text
        resume.source_file_url = source_url
    else:
        text_clean = text.strip()
        entities = await resume_service.extract_entities_from_text(
            text_clean, run_agent=validate
        )
        resume.entities = entities
        resume.raw_text = text_clean
        resume.source_file_url = None

    await session.commit()
    await session.refresh(resume)

    payload = ResumeExtractResponse(
        entities=resume.entities,
        raw_text=resume.raw_text,
        resume_id=resume.id,
        source_file_url=resume.source_file_url,
    )
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
    "/{resume_id}",
    response_model=CommonResponse[DeleteResumeResponse],
    name="Delete resume by ID",
    summary="Delete a single resume by ID.",
)
async def delete_resume(
    resume_id: uuid_pkg.UUID = Path(..., description="Resume ID to delete."),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Deletes the resume if it belongs to the current user. Returns 404 if not found or not owned.
    """
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")
    await session.delete(resume)
    await session.commit()
    return CommonResponse(
        success=True,
        message="Resume deleted successfully",
        payload=DeleteResumeResponse(deleted=True),
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
