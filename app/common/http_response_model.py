"""
Standard API response wrapper for consistent JSON shape.
"""

from typing import Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict

DataT = TypeVar("DataT")


class PageMeta(BaseModel):
    """Pagination metadata (for future use)."""

    model_config = ConfigDict(from_attributes=True)
    page: int
    page_size: int
    total_pages: int
    total_items: int


class CommonResponse(BaseModel, Generic[DataT]):
    """Standard response: success, message, payload, optional meta."""

    model_config = ConfigDict(from_attributes=True)
    success: bool
    message: str
    payload: Optional[Union[DataT, List[DataT]]] = None
    meta: Optional[PageMeta] = None
