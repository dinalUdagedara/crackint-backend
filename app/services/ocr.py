"""
Common OCR service: extract text from image bytes.
Uses Tesseract via pytesseract. Can be used by resume, job, or any other feature that needs image-to-text.
Requires Tesseract OCR to be installed on the system (e.g. apt install tesseract-ocr, brew install tesseract).
"""

from typing import Any, Optional

# Supported image types for OCR (content-type -> PIL format hint)
SUPPORTED_IMAGE_CONTENT_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
})

# Magic bytes for detection when content_type is missing or generic
_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),  # WebP starts with RIFF....WEBP
]


def _preprocess_for_ocr(img: Any) -> Any:
    """
    Preprocess image for Tesseract: grayscale, contrast boost, optional resize.
    Improves OCR on colored posters, screenshots, and low-contrast images.
    """
    from PIL import Image, ImageEnhance

    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    # Grayscale often improves Tesseract on colored/mixed backgrounds
    if img.mode != "L":
        img = img.convert("L")
    # Slight contrast boost helps text stand out
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.3)
    # Resize if too small (Tesseract works better with ~300 DPI equivalent)
    w, h = img.size
    min_side = 1000
    if w < min_side and h < min_side:
        scale = min_side / max(w, h) if max(w, h) > 0 else 1
        if scale > 1:
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)
    return img


def _detect_image_content_type(content: bytes) -> Optional[str]:
    """Infer image content type from magic bytes. Returns None if not recognized."""
    if len(content) < 12:
        return None
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def extract_text_from_image(
    content: bytes,
    content_type: Optional[str] = None,
) -> str:
    """
    Extract text from image bytes using Tesseract OCR.

    Args:
        content: Raw image file bytes.
        content_type: Optional MIME type (e.g. image/png, image/jpeg). If None, inferred from magic bytes.

    Returns:
        Extracted text as a single string. May be empty if no text found.

    Raises:
        ValueError: If content is not a supported image, or if Tesseract is not available.
    """
    if not content or len(content) < 4:
        raise ValueError("Empty or invalid image content")

    if content_type is None or content_type == "application/octet-stream":
        content_type = _detect_image_content_type(content)
    if content_type is None:
        raise ValueError("Could not determine image type; use PNG, JPEG, or WebP")

    content_type = content_type.lower().strip()
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in SUPPORTED_IMAGE_CONTENT_TYPES:
        raise ValueError(f"Unsupported image type: {content_type}. Use image/png, image/jpeg, or image/webp.")

    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"Invalid image: {e}") from e

    # Preprocess for better OCR on posters/screenshots: grayscale, contrast, optional resize
    img = _preprocess_for_ocr(img)

    try:
        import pytesseract
        # PSM 3 = fully automatic; 6 = uniform block. Use 3 for posters with multiple sections.
        text = pytesseract.image_to_string(img, config="--psm 3")
    except pytesseract.TesseractNotFoundError:
        raise ValueError(
            "Tesseract OCR is not installed. Install it on your system (e.g. apt install tesseract-ocr or brew install tesseract) and ensure it is on PATH."
        ) from None
    except Exception as e:
        raise ValueError(f"OCR failed: {e}") from e

    return (text or "").strip()
