from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.response import success
from schemas.offline_downloads import OfflineDownloadCreate
from services.auth import User, get_current_active_user
from services.logging import LogService
from services.task_queue import task_queue_service, TaskProgress
from services.virtual_fs import path_is_directory


router = APIRouter(
    prefix="/api/offline-downloads",
    tags=["OfflineDownloads"],
)


@router.post("/")
async def create_offline_download(
    payload: OfflineDownloadCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    dest_dir = payload.dest_dir
    try:
        is_dir = await path_is_directory(dest_dir)
    except HTTPException:
        is_dir = False
    if not is_dir:
        raise HTTPException(400, detail="Destination directory not found")

    task = await task_queue_service.add_task(
        "offline_http_download",
        {
            "url": str(payload.url),
            "dest_dir": dest_dir,
            "filename": payload.filename,
        },
    )

    await task_queue_service.update_progress(
        task.id,
        TaskProgress(
            stage="queued",
            percent=0.0,
            bytes_total=None,
            bytes_done=0,
            detail="Waiting to start",
        ),
    )

    await LogService.action(
        "route:offline_downloads",
        f"Offline download task created {task.id}",
        details={"url": str(payload.url), "dest_dir": dest_dir, "filename": payload.filename},
        user_id=current_user.id if hasattr(current_user, "id") else None,
    )

    return success({"task_id": task.id})


@router.get("/")
async def list_offline_downloads(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    tasks = [t for t in task_queue_service.get_all_tasks() if t.name == "offline_http_download"]
    data = [t.dict() for t in tasks]
    return success(data)


@router.get("/{task_id}")
async def get_offline_download(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    task = task_queue_service.get_task(task_id)
    if not task or task.name != "offline_http_download":
        raise HTTPException(status_code=404, detail="Task not found")
    return success(task.dict())
