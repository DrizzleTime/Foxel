from __future__ import annotations

import re
from dataclasses import asdict
from typing import Dict, List, Optional

from domain.automation.entities import AutomationRule
from domain.automation.repositories import AutomationTaskRepository
from domain.processors.repositories import ProcessorRegistry
from application.logging.dependencies import logging_service
from application.task_queue import TaskProgress, task_queue_service


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


class AutomationService:
    def __init__(
        self,
        repository: AutomationTaskRepository,
        processor_registry: ProcessorRegistry,
    ):
        self._repository = repository
        self._processor_registry = processor_registry

    async def list_tasks(self) -> List[AutomationRule]:
        return await self._repository.list_all()

    async def get_task(self, task_id: int) -> AutomationRule | None:
        return await self._repository.get(task_id)

    async def create_task(self, payload: Dict) -> AutomationRule:
        self._ensure_processor(payload.get("processor_type"))
        rule = AutomationRule(
            id=0,
            name=payload["name"],
            event=payload["event"],
            path_pattern=payload.get("path_pattern"),
            filename_regex=payload.get("filename_regex"),
            processor_type=payload["processor_type"],
            processor_config=payload.get("processor_config") or {},
            enabled=bool(payload.get("enabled", True)),
        )
        return await self._repository.create(rule)

    async def update_task(self, task_id: int, payload: Dict) -> AutomationRule:
        if "processor_type" in payload:
            self._ensure_processor(payload["processor_type"])
        updates = {k: v for k, v in payload.items() if v is not None}
        updated = await self._repository.update(task_id, updates)
        if not updated:
            raise ValueError(f"Task {task_id} not found")
        return updated

    async def delete_task(self, task_id: int) -> bool:
        return await self._repository.delete(task_id)

    async def trigger(self, event: str, path: str):
        normalized_path = _normalize_path(path)
        candidates = await self._repository.list_enabled_by_event(event)
        matched: List[AutomationRule] = []
        for rule in candidates:
            if not self._matches(rule, normalized_path):
                continue
            matched.append(rule)

        for rule in matched:
            task = await task_queue_service.add_task(
                "automation_task",
                {"task_id": rule.id, "path": normalized_path},
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
            await logging_service.action(
                "automation",
                f"Automation task queued {task.id}",
                details={"rule": asdict(rule), "path": normalized_path},
            )

    def _matches(self, rule: AutomationRule, path: str) -> bool:
        if rule.path_pattern:
            prefix = _normalize_path(rule.path_pattern)
            if not (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
                return False
        if rule.filename_regex:
            try:
                pattern = re.compile(rule.filename_regex)
            except re.error:
                return False
            filename = path.rsplit("/", 1)[-1]
            if not pattern.search(filename):
                return False
        return True

    def _ensure_processor(self, processor_type: Optional[str]):
        if not processor_type:
            raise ValueError("processor_type is required")
        if not self._processor_registry.get_factory(processor_type):
            raise ValueError(f"Processor {processor_type} not found")


__all__ = ["AutomationService"]
