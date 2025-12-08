from fastapi import APIRouter, Depends, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth.service import get_current_active_user
from domain.tasks.service import TaskService
from domain.tasks.types import (
    AutomationTaskCreate,
    AutomationTaskUpdate,
    TaskQueueSettings,
)

CurrentUser = TaskService.current_user_dep

router = APIRouter(
    prefix="/api/tasks",
    tags=["Tasks"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


@router.get("/queue")
@audit(action=AuditAction.READ, description="获取任务队列状态")
async def get_task_queue_status(request: Request, current_user: CurrentUser):
    payload = TaskService.get_queue_tasks()
    return success(payload)


@router.get("/queue/settings")
@audit(action=AuditAction.READ, description="获取任务队列设置")
async def get_task_queue_settings(request: Request, current_user: CurrentUser):
    payload = TaskService.get_queue_settings()
    return success(payload.model_dump())


@router.post("/queue/settings")
@audit(
    action=AuditAction.UPDATE,
    description="更新任务队列设置",
    body_fields=["concurrency"],
)
async def update_task_queue_settings(request: Request, settings: TaskQueueSettings, current_user: CurrentUser):
    payload = await TaskService.update_queue_settings(settings, getattr(current_user, "id", None))
    return success(payload.model_dump())


@router.get("/queue/{task_id}")
@audit(action=AuditAction.READ, description="获取队列任务状态")
async def get_task_status(task_id: str, request: Request, current_user: CurrentUser):
    payload = TaskService.get_queue_task(task_id)
    return success(payload)


@router.post("/")
@audit(
    action=AuditAction.CREATE,
    description="创建自动化任务",
    body_fields=[
        "name",
        "event",
        "path_pattern",
        "filename_regex",
        "processor_type",
        "processor_config",
        "enabled",
    ],
    user_kw="user",
)
async def create_task(request: Request, task_in: AutomationTaskCreate, user: CurrentUser):
    task = await TaskService.create_task(task_in, user)
    return success(task)


@router.get("/{task_id}")
@audit(action=AuditAction.READ, description="获取自动化任务详情")
async def get_task(task_id: int, request: Request, current_user: CurrentUser):
    task = await TaskService.get_task(task_id)
    return success(task)


@router.get("/")
@audit(action=AuditAction.READ, description="获取自动化任务列表")
async def list_tasks(request: Request, current_user: CurrentUser):
    tasks = await TaskService.list_tasks()
    return success(tasks)


@router.put("/{task_id}")
@audit(
    action=AuditAction.UPDATE,
    description="更新自动化任务",
    body_fields=[
        "name",
        "event",
        "path_pattern",
        "filename_regex",
        "processor_type",
        "processor_config",
        "enabled",
    ],
)
async def update_task(request: Request, current_user: CurrentUser, task_id: int, task_in: AutomationTaskUpdate):
    task = await TaskService.update_task(task_id, task_in, current_user)
    return success(task)


@router.delete("/{task_id}")
@audit(action=AuditAction.DELETE, description="删除自动化任务", user_kw="user")
async def delete_task(task_id: int, request: Request, user: CurrentUser):
    await TaskService.delete_task(task_id, user)
    return success(msg="Task deleted")
