"""Admin API routes: users and global session listing."""

import uuid as uuid_pkg
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.schemas import (
    AdminSessionListItem,
    AdminUserDeletePayload,
    AdminUserListItem,
    AdminUserUpdate,
)
from app.api.admin.service import (
    delete_user_and_all_data,
    list_sessions_admin,
    list_users_admin,
)
from app.api.deps import get_current_admin_user, get_db
from app.common.http_response_model import CommonResponse, PageMeta
from app.models import User
from app.schemas.common import SessionStatus

router = APIRouter()

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get(
    "/users",
    response_model=CommonResponse[List[AdminUserListItem]],
    name="Admin list users",
    summary="List all users (paginated, optional search on email or name).",
)
async def admin_list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: Optional[str] = Query(
        default=None,
        description="Case-insensitive substring match on email or name.",
    ),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    items, total_items = await list_users_admin(
        db, page=page, page_size=page_size, search=search
    )
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    meta = PageMeta(
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_items=total_items,
    )
    return CommonResponse(
        success=True,
        message="Users retrieved successfully",
        payload=items,
        meta=meta,
    )


@router.patch(
    "/users/{user_id}",
    response_model=CommonResponse[AdminUserListItem],
    name="Admin update user",
    summary="Update a user's name, email, and/or profile_image_url.",
)
async def admin_update_user(
    user_id: uuid_pkg.UUID,
    body: AdminUserUpdate,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalars().one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if "email" in updates and updates["email"] != target.email:
        dup = await db.execute(select(User).where(User.email == updates["email"]))
        if dup.scalars().one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        target.email = updates["email"]
    if "name" in updates:
        target.name = updates["name"]
    if "profile_image_url" in updates:
        target.profile_image_url = updates["profile_image_url"]

    db.add(target)
    await db.commit()
    await db.refresh(target)
    return CommonResponse(
        success=True,
        message="User updated successfully",
        payload=AdminUserListItem.model_validate(target),
    )


@router.delete(
    "/users/{user_id}",
    response_model=CommonResponse[AdminUserDeletePayload],
    name="Admin delete user",
    summary="Delete a user and all related data (sessions, resumes, jobs, cover letters, etc.).",
)
async def admin_delete_user(
    user_id: uuid_pkg.UUID,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete your own account",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalars().one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    ps, cl, r, j = await delete_user_and_all_data(db, user_id)
    return CommonResponse(
        success=True,
        message="User and related data deleted successfully",
        payload=AdminUserDeletePayload(
            deleted_user_id=user_id,
            prep_sessions_deleted=ps,
            cover_letters_deleted=cl,
            resumes_deleted=r,
            job_postings_deleted=j,
        ),
    )


@router.get(
    "/sessions",
    response_model=CommonResponse[List[AdminSessionListItem]],
    name="Admin list prep sessions",
    summary="List all prep sessions with optional filters (paginated).",
)
async def admin_list_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status_filter: Optional[SessionStatus] = Query(
        default=None,
        alias="status",
        description="Filter by session status (ACTIVE or COMPLETED).",
    ),
    user_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Filter sessions by owning user ID.",
    ),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    items, total_items = await list_sessions_admin(
        db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        user_id_filter=user_id,
    )
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    meta = PageMeta(
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_items=total_items,
    )
    return CommonResponse(
        success=True,
        message="Sessions retrieved successfully",
        payload=items,
        meta=meta,
    )
