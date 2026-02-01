"""
Central API router: include all feature routers under /api/v1.
"""

from fastapi import APIRouter

from app.api.health.route import router as health_router
from app.api.resume.route import router as resume_router
from app.api.job.route import router as job_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(resume_router, prefix="/resumes", tags=["resumes"])
api_router.include_router(job_router, prefix="/jobs", tags=["jobs"])
