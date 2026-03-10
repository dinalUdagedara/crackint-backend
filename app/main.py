"""
FastAPI application factory. Used by server.py and uvicorn.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.common.http_response_model import CommonResponse
from app.config import settings
from app.ml.resume_ner import load_model as load_resume_ner
from app.ml.job_poster_ner import load_model as load_job_poster_ner
from app.ws.ws_manager import create_sio_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load NER models at startup when respective load dirs are set."""
    load_resume_ner()
    load_job_poster_ner()
    yield
    # optional: cleanup on shutdown


def get_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0",
        docs_url=f"{settings.API_PREFIX}/docs",
        redoc_url=f"{settings.API_PREFIX}/redoc",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {
            "message": "Crackint Backend API",
            "docs": f"{settings.API_PREFIX}/docs",
            "health": f"{settings.API_PREFIX}/health",
        }

    app.include_router(api_router, prefix=settings.API_PREFIX)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=CommonResponse(
                success=False,
                message="Validation error",
                payload=exc.errors(),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(_request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=CommonResponse(
                success=False,
                message="Internal server error",
                payload=None,
            ).model_dump(),
        )

    # Wrap FastAPI with Socket.IO
    return create_sio_app(app)
