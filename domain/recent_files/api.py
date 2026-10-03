from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.response import success
from domain.auth import User, get_current_active_user

from .service import RecentFilesService
from .types import RecordRecentFileRequest

router = APIRouter(prefix="/api/fs/recent", tags=["recent-files"])


@router.get("/")
async def list_recent_files(
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = Query(20, ge=1, le=200, description="返回数量"),
):
    data = await RecentFilesService.list_recent_files(current_user.id, limit)
    return success(data)


@router.post("/")
async def record_recent_file(
    body: RecordRecentFileRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await RecentFilesService.record_opened_file(current_user.id, body.path)
    return success(data)


@router.delete("/")
async def clear_recent_files(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await RecentFilesService.clear_recent_files(current_user.id)
    return success(data)
