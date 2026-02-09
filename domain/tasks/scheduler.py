import asyncio
from dataclasses import dataclass
from datetime import datetime

from croniter import croniter

from models.database import AutomationTask
from .task_queue import task_queue_service


@dataclass
class CronTaskItem:
    task_id: int
    processor_type: str
    path: str
    cron: croniter
    next_run: datetime


class AutomationTaskScheduler:
    def __init__(self):
        self._items: list[CronTaskItem] = []
        self._worker: asyncio.Task | None = None
        self._reload_event = asyncio.Event()
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._worker and not self._worker.done():
            return
        self._stop_event.clear()
        await self._load_tasks()
        self._worker = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._worker:
            return
        self._stop_event.set()
        self._reload_event.set()
        await self._worker
        self._worker = None

    def refresh(self) -> None:
        if self._worker and not self._worker.done():
            self._reload_event.set()

    async def _load_tasks(self) -> None:
        tasks = await AutomationTask.filter(event="cron", enabled=True)
        items: list[CronTaskItem] = []
        now = datetime.now()
        for task in tasks:
            trigger = task.trigger_config or {}
            if not isinstance(trigger, dict):
                continue
            cron_expr = trigger.get("cron_expr")
            path = trigger.get("path")
            if not cron_expr or not path:
                continue
            cron = self._build_cron(cron_expr, now)
            if not cron:
                continue
            next_run = cron.get_next(datetime)
            items.append(
                CronTaskItem(
                    task_id=task.id,
                    processor_type=task.processor_type,
                    path=path,
                    cron=cron,
                    next_run=next_run,
                )
            )
        self._items = items

    def _build_cron(self, expr: str, base_time: datetime) -> croniter | None:
        expr = str(expr or "").strip()
        if not expr:
            return None
        parts = [p for p in expr.split() if p]
        if len(parts) not in (5, 6):
            return None
        second_at_beginning = len(parts) == 6
        try:
            return croniter(expr, base_time, second_at_beginning=second_at_beginning)
        except Exception:
            return None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._reload_event.is_set():
                self._reload_event.clear()
                await self._load_tasks()
            now = datetime.now()
            for item in list(self._items):
                if item.next_run <= now:
                    await task_queue_service.add_task(
                        item.processor_type,
                        {"task_id": item.task_id, "path": item.path},
                    )
                    item.next_run = item.cron.get_next(datetime)
            await asyncio.sleep(1)


task_scheduler = AutomationTaskScheduler()
