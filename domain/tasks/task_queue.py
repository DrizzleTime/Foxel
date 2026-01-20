import asyncio
from typing import Dict, Any
from pydantic import BaseModel, Field
import uuid
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
        task.status = TaskStatus.RUNNING

        try:
            # Local import to avoid circular dependency during module load.
            from domain.virtual_fs import VirtualFSService

            if task.name == "process_file":
                params = task.task_info
                result = await VirtualFSService.process_file(
                    path=params["path"],
                    processor_type=params["processor_type"],
                    config=params["config"],
                    save_to=params.get("save_to"),
                    overwrite=params.get("overwrite", False),
                )
                task.result = result
            elif task.name == "process_directory_scan":
                from domain.processors import ProcessDirectoryRequest, ProcessorService

                params = task.task_info or {}
                req = ProcessDirectoryRequest(**params)
                task.result = await ProcessorService.scan_directory(req)
            elif task.name == "automation_task" or self._is_processor_task(task.name):
                from models.database import AutomationTask

                params = task.task_info
                auto_task = await AutomationTask.get(id=params["task_id"])
                path = params["path"]

                processor_type = auto_task.processor_type
                config = auto_task.processor_config or {}
                save_to = config.get("save_to") if isinstance(config, dict) else None
                overwrite = bool(config.get("overwrite")) if isinstance(config, dict) else False
                try:
                    if await VirtualFSService.path_is_directory(path):
                        overwrite = True
                except Exception:
                    pass
                await VirtualFSService.process_file(
                    path=path,
                    processor_type=processor_type,
                    config=config if isinstance(config, dict) else {},
                    save_to=save_to,
                    overwrite=overwrite,
                )
                task.result = "Automation task completed"
            elif task.name == "offline_http_download":
                from domain.offline_downloads import OfflineDownloadService

                result_path = await OfflineDownloadService.run_http_download(task)
                task.result = {"path": result_path}
            elif task.name == "cross_mount_transfer":
                result = await VirtualFSService.run_cross_mount_transfer_task(task)
                task.result = result
            elif task.name == "send_email":
                from domain.email import EmailService
                await EmailService.send_from_task(task.id, task.task_info)
                task.result = "Email sent"
            else:
                raise ValueError(f"Unknown task name: {task.name}")
            task.status = TaskStatus.SUCCESS

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)

    def _cleanup_workers(self):
        self._worker_tasks = [task for task in self._worker_tasks if not task.done()]

    def _is_processor_task(self, task_name: str) -> bool:
        try:
            from domain.processors import get_processor

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
        elif current > self._concurrency:
            for _ in range(current - self._concurrency):
                await self._queue.put(_SENTINEL)

    async def _worker_loop(self, worker_id: int):
        current_task = asyncio.current_task()
        try:
            while True:
                job = await self._queue.get()
                if job is _SENTINEL:
                    self._queue.task_done()
                    break
                try:
                    await self._execute_task(job)
                except Exception as e:
                    pass
                finally:
                    self._queue.task_done()
        finally:
            if current_task in self._worker_tasks:
                self._worker_tasks.remove(current_task)  # type: ignore[arg-type]

    async def start_worker(self, concurrency: int | None = None):
        if concurrency is None:
            from domain.config import ConfigService

            stored_value = await ConfigService.get("TASK_QUEUE_CONCURRENCY", self._concurrency)
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

    def get_concurrency(self) -> int:
        return self._concurrency

    def get_active_worker_count(self) -> int:
        self._cleanup_workers()
        return len(self._worker_tasks)


task_queue_service = TaskQueueService()
