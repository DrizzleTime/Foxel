from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated

from models.database import AutomationTask
from schemas.tasks import (
    AutomationTaskCreate,
    AutomationTaskUpdate,
    TaskQueueSettings,
    TaskQueueSettingsResponse,
)
from api.response import success
from services.auth import get_current_active_user, User
from services.logging import LogService
from services.task_queue import task_queue_service
from services.config import ConfigCenter

router = APIRouter(
    prefix="/api/tasks",
    tags=["Tasks"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


@router.get("/queue")
async def get_task_queue_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    tasks = task_queue_service.get_all_tasks()
    return success([task.dict() for task in tasks])


@router.get("/queue/settings")
async def get_task_queue_settings(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    payload = TaskQueueSettingsResponse(
        concurrency=task_queue_service.get_concurrency(),
        active_workers=task_queue_service.get_active_worker_count(),
    )
    return success(payload.model_dump())


@router.post("/queue/settings")
async def update_task_queue_settings(
    settings: TaskQueueSettings,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    await task_queue_service.set_concurrency(settings.concurrency)
    await ConfigCenter.set("TASK_QUEUE_CONCURRENCY", str(task_queue_service.get_concurrency()))
    await LogService.action(
        "route:tasks",
        "Updated task queue settings",
        details={"concurrency": settings.concurrency},
        user_id=getattr(current_user, "id", None),
    )
    payload = TaskQueueSettingsResponse(
        concurrency=task_queue_service.get_concurrency(),
        active_workers=task_queue_service.get_active_worker_count(),
    )
    return success(payload.model_dump())


@router.get("/queue/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    task = task_queue_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return success(task.dict())


@router.post("/")
async def create_task(
    task_in: AutomationTaskCreate,
    user: User = Depends(get_current_active_user)
):
    task = await AutomationTask.create(**task_in.model_dump())
    await LogService.action(
        "route:tasks",
        f"Created task {task.name}",
        details=task_in.model_dump(),
        user_id=user.id if hasattr(user, "id") else None,
    )
    return success(task)


@router.get("/{task_id}")
async def get_task(task_id: int):
    task = await AutomationTask.get_or_none(id=task_id)
    if not task:
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found")
    return success(task)


@router.get("/")
async def list_tasks():
    tasks = await AutomationTask.all()
    return success(tasks)


@router.put("/{task_id}")
async def update_task(
        current_user: Annotated[User, Depends(get_current_active_user)],
        task_id: int, task_in: AutomationTaskUpdate):
    task = await AutomationTask.get_or_none(id=task_id)
    if not task:
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found")
    update_data = task_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)
    await task.save()
    await LogService.action(
        "route:tasks",
        f"Updated task {task.name}",
        details=task_in.model_dump(),
        user_id=current_user.id,
    )
    return success(task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    user: User = Depends(get_current_active_user)
):
    deleted_count = await AutomationTask.filter(id=task_id).delete()
    if not deleted_count:
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found")
    await LogService.action(
        "route:tasks",
        f"Deleted task {task_id}",
        details={"task_id": task_id},
        user_id=user.id if hasattr(user, "id") else None,
    )
    return success(msg="Task deleted")
