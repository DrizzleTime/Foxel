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


class TaskProgress(BaseModel):
    stage: str | None = None
    percent: float | None = None
    bytes_total: int | None = None
    bytes_done: int | None = None
    detail: str | None = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    task_info: Dict[str, Any] = {}
    progress: TaskProgress | None = None
    meta: Dict[str, Any] | None = None


_SENTINEL = object()


class TaskQueueService:
    def __init__(self):
        self._queue: asyncio.Queue[Task | object] = asyncio.Queue()
        self._tasks: Dict[str, Task] = {}
        self._worker_tasks: list[asyncio.Task] = []
        self._concurrency: int = 1
        self._worker_seq: int = 0

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

    async def update_progress(self, task_id: str, progress: TaskProgress | Dict[str, Any]):
        task = self._tasks.get(task_id)
        if not task:
            return
        if isinstance(progress, TaskProgress):
            task.progress = progress
        else:
            task.progress = TaskProgress(**progress)

    async def update_meta(self, task_id: str, meta: Dict[str, Any]):
        task = self._tasks.get(task_id)
        if not task:
            return
        task.meta = (task.meta or {}) | meta

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
            elif task.name == "automation_task" or self._is_processor_task(task.name):
                from models.database import AutomationTask
                from services.processors.registry import get as get_processor
                from services.virtual_fs import read_file, write_file

                params = task.task_info
                auto_task = await AutomationTask.get(id=params["task_id"])
                path = params["path"]

                processor_type = auto_task.processor_type if task.name == "automation_task" else task.name
                processor = get_processor(processor_type)
                if not processor:
                    raise ValueError(f"Processor {processor_type} not found for task {auto_task.id}")

                if processor_type != auto_task.processor_type:
                    await LogService.warning(
                        "task_queue",
                        "Processor type mismatch; falling back to stored type",
                        {"task_id": auto_task.id, "expected": auto_task.processor_type, "got": processor_type},
                    )
                    processor_type = auto_task.processor_type
                    processor = get_processor(processor_type)
                    if not processor:
                        raise ValueError(f"Processor {processor_type} not found for task {auto_task.id}")

                file_content = await read_file(path)
                result = await processor.process(file_content, path, auto_task.processor_config)
                
                save_to = auto_task.processor_config.get("save_to")
                if save_to and getattr(processor, "produces_file", False):
                    await write_file(save_to, result)
                task.result = "Automation task completed"
            elif task.name == "offline_http_download":
                from services.offline_download import run_http_download

                result_path = await run_http_download(task)
                task.result = {"path": result_path}
            elif task.name == "cross_mount_transfer":
                from services.virtual_fs import run_cross_mount_transfer_task

                result = await run_cross_mount_transfer_task(task)
                task.result = result
            elif task.name == "send_email":
                from services.email import EmailService
                await EmailService.send_from_task(task.id, task.task_info)
                task.result = "Email sent"
            else:
                raise ValueError(f"Unknown task name: {task.name}")
            
            task.status = TaskStatus.SUCCESS
            await LogService.info("task_queue", f"Task {task.name} ({task.id}) succeeded", {"task_id": task.id, "name": task.name})

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            await LogService.error("task_queue", f"Task {task.name} ({task.id}) failed: {e}", {"task_id": task.id, "name": task.name})

    def _cleanup_workers(self):
        self._worker_tasks = [task for task in self._worker_tasks if not task.done()]

    def _is_processor_task(self, task_name: str) -> bool:
        try:
            from services.processors.registry import get as get_processor

            return get_processor(task_name) is not None
        except Exception:
            return False

    async def _ensure_worker_count(self):
        self._cleanup_workers()
        current = len(self._worker_tasks)
        if current < self._concurrency:
            for _ in range(self._concurrency - current):
                self._worker_seq += 1
                worker_id = self._worker_seq
                worker_task = asyncio.create_task(self._worker_loop(worker_id))
                self._worker_tasks.append(worker_task)
            await LogService.info("task_queue", "Task workers adjusted", {"active_workers": len(self._worker_tasks), "target": self._concurrency})
        elif current > self._concurrency:
            for _ in range(current - self._concurrency):
                await self._queue.put(_SENTINEL)
            await LogService.info("task_queue", "Task workers scaling down", {"active_workers": len(self._worker_tasks), "target": self._concurrency})

    async def _worker_loop(self, worker_id: int):
        current_task = asyncio.current_task()
        await LogService.info("task_queue", f"Worker {worker_id} started")
        try:
            while True:
                job = await self._queue.get()
                if job is _SENTINEL:
                    self._queue.task_done()
                    break
                try:
                    await self._execute_task(job)
                except Exception as e:
                    await LogService.error(
                        "task_queue",
                        f"Error executing task {job.id}: {e}",
                        {"task_id": job.id, "name": job.name},
                    )
                finally:
                    self._queue.task_done()
        finally:
            if current_task in self._worker_tasks:
                self._worker_tasks.remove(current_task)  # type: ignore[arg-type]
            await LogService.info("task_queue", f"Worker {worker_id} stopped")

    async def start_worker(self, concurrency: int | None = None):
        if concurrency is None:
            from services.config import ConfigCenter

            stored_value = await ConfigCenter.get("TASK_QUEUE_CONCURRENCY", self._concurrency)
            try:
                concurrency = int(stored_value)
            except (TypeError, ValueError):
                concurrency = self._concurrency
        await self.set_concurrency(concurrency)

    async def set_concurrency(self, value: int):
        value = max(1, int(value))
        if value != self._concurrency:
            self._concurrency = value
        await self._ensure_worker_count()

    async def stop_worker(self):
        self._cleanup_workers()
        for _ in range(len(self._worker_tasks)):
            await self._queue.put(_SENTINEL)
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        await LogService.info("task_queue", "Task workers have been stopped.")

    def get_concurrency(self) -> int:
        return self._concurrency

    def get_active_worker_count(self) -> int:
        self._cleanup_workers()
        return len(self._worker_tasks)


task_queue_service = TaskQueueService()
