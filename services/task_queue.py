import asyncio
from typing import Dict, Any
from pydantic import BaseModel, Field
import uuid
from services.logging import LogService
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    task_info: Dict[str, Any] = {}


class TaskQueueService:
    def __init__(self):
        self._queue = asyncio.Queue()
        self._tasks: Dict[str, Task] = {}
        self._worker_task: asyncio.Task | None = None

    async def add_task(self, name: str, task_info: Dict[str, Any]) -> Task:
        task = Task(name=name, task_info=task_info)
        self._tasks[task.id] = task
        await self._queue.put(task)
        await LogService.info("task_queue", f"Task {name} ({task.id}) enqueued", {"task_id": task.id, "name": name})
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    async def _execute_task(self, task: Task):
        from services.virtual_fs import process_file

        task.status = TaskStatus.RUNNING
        await LogService.info("task_queue", f"Task {task.name} ({task.id}) started", {"task_id": task.id, "name": task.name})

        try:
            if task.name == "process_file":
                params = task.task_info
                result = await process_file(
                    path=params["path"],
                    processor_type=params["processor_type"],
                    config=params["config"],
                    save_to=params.get("save_to"),
                    overwrite=params.get("overwrite", False),
                )
                task.result = result
            elif task.name == "automation_task":
                from models.database import AutomationTask
                from services.processors.registry import get as get_processor
                from services.virtual_fs import read_file, write_file

                params = task.task_info
                auto_task = await AutomationTask.get(id=params["task_id"])
                path = params["path"]

                processor = get_processor(auto_task.processor_type)
                if not processor:
                    raise ValueError(f"Processor {auto_task.processor_type} not found for task {auto_task.id}")

                file_content = await read_file(path)
                result = await processor.process(file_content, path, auto_task.processor_config)
                
                save_to = auto_task.processor_config.get("save_to")
                if save_to and getattr(processor, "produces_file", False):
                    await write_file(save_to, result)
                task.result = "Automation task completed"
            else:
                raise ValueError(f"Unknown task name: {task.name}")
            
            task.status = TaskStatus.SUCCESS
            await LogService.info("task_queue", f"Task {task.name} ({task.id}) succeeded", {"task_id": task.id, "name": task.name})

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            await LogService.error("task_queue", f"Task {task.name} ({task.id}) failed: {e}", {"task_id": task.id, "name": task.name})

    async def worker(self):
        await LogService.info("task_queue", "Task worker started")
        while True:
            try:
                task = await self._queue.get()
                await self._execute_task(task)
            except asyncio.CancelledError:
                await LogService.info("task_queue", "Task worker stopped")
                break
            except Exception as e:
                await LogService.error("task_queue", f"Error in task worker: {e}", exc_info=True)
            finally:
                self._queue.task_done()

    async def start_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self.worker())
            await LogService.info("task_queue", "Task worker created.")

    async def stop_worker(self):
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            finally:
                self._worker_task = None
                await LogService.info("task_queue", "Task worker has been stopped.")


task_queue_service = TaskQueueService()
