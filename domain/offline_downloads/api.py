from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth.service import get_current_active_user
from domain.auth.types import User
from domain.offline_downloads.service import OfflineDownloadService
from domain.offline_downloads.types import OfflineDownloadCreate

CurrentUser = Annotated[User, Depends(get_current_active_user)]

router = APIRouter(
    prefix="/api/offline-downloads",
    tags=["OfflineDownloads"],
)


@router.post("/")
@audit(
    action=AuditAction.CREATE,
    description="创建离线下载任务",
    body_fields=["url", "dest_dir", "filename"],
)
async def create_offline_download(request: Request, payload: OfflineDownloadCreate, current_user: CurrentUser):
    data = await OfflineDownloadService.create_download(payload, current_user)
    return success(data)


@router.get("/")
@audit(action=AuditAction.READ, description="获取离线下载列表")
async def list_offline_downloads(request: Request, current_user: CurrentUser):
    data = OfflineDownloadService.list_downloads()
    return success(data)


@router.get("/{task_id}")
@audit(action=AuditAction.READ, description="获取离线下载详情")
async def get_offline_download(task_id: str, request: Request, current_user: CurrentUser):
    data = OfflineDownloadService.get_download(task_id)
    return success(data)
