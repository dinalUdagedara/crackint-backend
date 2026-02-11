"""
Entry point: run the FastAPI app with uvicorn (factory mode).
"""

import logging

import uvicorn

from app.config import settings

# Ensure app loggers (resume extract, entity agent, etc.) show INFO in the console
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.INFO)
# Reduce httpx noise (OpenAI client) so "HTTP Request: POST ..." is not logged at INFO
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:get_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        factory=True,
    )
