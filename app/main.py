"""
FastAPI application factory. Used by server.py and uvicorn.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.common.http_response_model import CommonResponse
from app.config import settings


def get_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0",
        docs_url=f"{settings.API_PREFIX}/docs",
        redoc_url=f"{settings.API_PREFIX}/redoc",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
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

    return app
