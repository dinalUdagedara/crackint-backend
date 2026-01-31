"""
Entry point: run the FastAPI app with uvicorn (factory mode).
"""

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:get_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        factory=True,
    )
