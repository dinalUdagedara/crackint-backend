"""
Entry point for 'fastapi dev main.py' or 'uvicorn main:app'.
Uses the full app (resume extract, health, docs at /api/v1/docs).
"""

from app.main import get_app

app = get_app()
