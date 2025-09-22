import re
from typing import List
from models.database import AutomationTask
from services.processors.registry import get as get_processor
from services.logging import LogService

from services.task_queue import task_queue_service


class TaskService:
    async def trigger_tasks(self, event: str, path: str):
        tasks = await AutomationTask.filter(event=event, enabled=True)
        for task in tasks:
            if self.match(task, path):
                await self.execute(task, path)

    def match(self, task: AutomationTask, path: str) -> bool:
        if task.path_pattern and not path.startswith(task.path_pattern):
            return False
        if task.filename_regex:
            filename = path.split('/')[-1]
            if not re.match(task.filename_regex, filename):
                return False
        return True

    async def execute(self, task: AutomationTask, path: str):
        await task_queue_service.add_task(
            task.processor_type,
            {
                "task_id": task.id,
                "path": path,
            },
        )

task_service = TaskService()
