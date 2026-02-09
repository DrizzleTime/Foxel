import re
from typing import Annotated, Any, Dict, Optional

from fastapi import Depends, HTTPException

from domain.auth import User, get_current_active_user
from domain.config import ConfigService
from .scheduler import task_scheduler
from .task_queue import task_queue_service
from .types import (
    AutomationTaskCreate,
    AutomationTaskUpdate,
    TaskQueueSettings,
    TaskQueueSettingsResponse,
)
from models.database import AutomationTask


class TaskService:
    current_user_dep = Annotated[User, Depends(get_current_active_user)]

    @classmethod
    def get_queue_tasks(cls) -> list[dict[str, Any]]:
        tasks = task_queue_service.get_all_tasks()
        return [task.dict() for task in tasks]

    @classmethod
    def get_queue_settings(cls) -> TaskQueueSettingsResponse:
        return TaskQueueSettingsResponse(
            concurrency=task_queue_service.get_concurrency(),
            active_workers=task_queue_service.get_active_worker_count(),
        )

    @classmethod
    async def update_queue_settings(cls, settings: TaskQueueSettings, user_id: Optional[int]) -> TaskQueueSettingsResponse:
        await task_queue_service.set_concurrency(settings.concurrency)
        await ConfigService.set("TASK_QUEUE_CONCURRENCY", str(task_queue_service.get_concurrency()))
        return cls.get_queue_settings()

    @classmethod
    def get_queue_task(cls, task_id: str) -> dict[str, Any]:
        task = task_queue_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task.dict()

    @classmethod
    async def create_task(cls, payload: AutomationTaskCreate, user: Optional[User]) -> AutomationTask:
        task = await AutomationTask.create(**payload.model_dump())
        task_scheduler.refresh()
        return task

    @classmethod
    async def get_task(cls, task_id: int) -> AutomationTask:
        task = await AutomationTask.get_or_none(id=task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return task

    @classmethod
    async def list_tasks(cls) -> list[AutomationTask]:
        tasks = await AutomationTask.all()
        return tasks

    @classmethod
    async def update_task(cls, task_id: int, payload: AutomationTaskUpdate, current_user: User) -> AutomationTask:
        task = await AutomationTask.get_or_none(id=task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(task, key, value)
        await task.save()
        task_scheduler.refresh()
        return task

    @classmethod
    async def delete_task(cls, task_id: int, user: Optional[User]) -> None:
        deleted_count = await AutomationTask.filter(id=task_id).delete()
        if not deleted_count:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        task_scheduler.refresh()

    @classmethod
    async def trigger_tasks(cls, event: str, path: str):
        tasks = await AutomationTask.filter(event=event, enabled=True)
        for task in tasks:
            if cls.match(task, path):
                await cls.execute(task, path)

    @classmethod
    def match(cls, task: AutomationTask, path: str) -> bool:
        trigger_config = task.trigger_config or {}
        if not isinstance(trigger_config, dict):
            trigger_config = {}
        path_prefix = trigger_config.get("path_prefix")
        filename_regex = trigger_config.get("filename_regex")
        if path_prefix and not path.startswith(path_prefix):
            return False
        if filename_regex:
            filename = path.split("/")[-1]
            if not re.match(filename_regex, filename):
                return False
        return True

    @classmethod
    async def execute(cls, task: AutomationTask, path: str):
        await task_queue_service.add_task(
            task.processor_type,
            {
                "task_id": task.id,
                "path": path,
            },
        )


task_service = TaskService
