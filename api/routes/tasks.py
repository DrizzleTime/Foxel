from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.response import success
from application.auth.dependencies import User, get_current_active_user
from application.automation.dependencies import automation_service
from application.config.dependencies import config_service
from application.logging.dependencies import logging_service
from application.task_queue import task_queue_service
from schemas.tasks import (
    AutomationTaskCreate,
    AutomationTaskUpdate,
    TaskQueueSettings,
    TaskQueueSettingsResponse,
)

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
    await config_service.set("TASK_QUEUE_CONCURRENCY", str(task_queue_service.get_concurrency()))
    await logging_service.action(
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
    try:
        task = await automation_service.create_task(task_in.model_dump())
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    await logging_service.action(
        "route:tasks",
        f"Created task {task.name}",
        details=task_in.model_dump(),
        user_id=user.id if hasattr(user, "id") else None,
    )
    return success(asdict(task))


@router.get("/{task_id}")
async def get_task(task_id: int):
    task = await automation_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found")
    return success(asdict(task))


@router.get("/")
async def list_tasks():
    tasks = await automation_service.list_tasks()
    return success([asdict(t) for t in tasks])


@router.put("/{task_id}")
async def update_task(
        current_user: Annotated[User, Depends(get_current_active_user)],
        task_id: int, task_in: AutomationTaskUpdate):
    update_data = task_in.model_dump(exclude_unset=True)
    try:
        task = await automation_service.update_task(task_id, update_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=404 if "not found" in str(exc) else 400, detail=str(exc)
        )
    await logging_service.action(
        "route:tasks",
        f"Updated task {task.name}",
        details=task_in.model_dump(),
        user_id=current_user.id,
    )
    return success(asdict(task))


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    user: User = Depends(get_current_active_user)
):
    deleted_count = await automation_service.delete_task(task_id)
    if not deleted_count:
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found")
    await logging_service.action(
        "route:tasks",
        f"Deleted task {task_id}",
        details={"task_id": task_id},
        user_id=user.id if hasattr(user, "id") else None,
    )
    return success(msg="Task deleted")
