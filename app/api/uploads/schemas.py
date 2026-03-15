"""Schemas for upload endpoints."""

from pydantic import BaseModel, ConfigDict


class UploadImageResponse(BaseModel):
    """Response after uploading an image; contains the public URL."""

    model_config = ConfigDict(from_attributes=True)
    url: str
