FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System packages needed by PyMuPDF/Pillow/pytesseract workflows.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# Install CPU-only torch first — the default index pulls ~3-4GB of unused NVIDIA/CUDA
# packages that do nothing on any of our (CPU-only) deploy targets. This satisfies the
# "torch>=2.0.0" constraint in requirements.txt so the next step won't reinstall it.
RUN pip install --upgrade pip \
    && pip install --retries 10 --timeout 120 torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --retries 10 --timeout 120 -r /app/requirements.txt

COPY . /app

EXPOSE 8000

# Production server command (no auto-reload)
CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
