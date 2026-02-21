"""
Central API router: include all feature routers under /api/v1.
"""

from fastapi import APIRouter

from app.api.auth.route import router as auth_router
from app.api.health.route import router as health_router
from app.api.resume.route import router as resume_router
from app.api.job.route import router as job_router
from app.api.job_posting.route import router as job_posting_router
from app.api.session.route import router as session_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(resume_router, prefix="/resumes", tags=["resumes"])
api_router.include_router(job_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(job_posting_router, prefix="/job-postings", tags=["job-postings"])
api_router.include_router(session_router, prefix="/sessions", tags=["sessions"])
