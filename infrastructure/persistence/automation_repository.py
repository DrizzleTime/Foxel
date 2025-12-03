from __future__ import annotations

from typing import Dict, Iterable, List

from domain.automation.entities import AutomationRule
from domain.automation.repositories import AutomationTaskRepository
from models.database import AutomationTask


def _to_entity(record: AutomationTask) -> AutomationRule:
    return AutomationRule(
        id=record.id,
        name=record.name,
        event=record.event,
        path_pattern=record.path_pattern,
        filename_regex=record.filename_regex,
        processor_type=record.processor_type,
        processor_config=record.processor_config or {},
        enabled=record.enabled,
    )


class TortoiseAutomationTaskRepository(AutomationTaskRepository):
    async def list_all(self) -> List[AutomationRule]:
        records: Iterable[AutomationTask] = await AutomationTask.all()
        return [_to_entity(rec) for rec in records]

    async def list_enabled_by_event(self, event: str) -> List[AutomationRule]:
        records: Iterable[AutomationTask] = await AutomationTask.filter(
            enabled=True, event=event
        )
        return [_to_entity(rec) for rec in records]

    async def get(self, task_id: int) -> AutomationRule | None:
        record = await AutomationTask.get_or_none(id=task_id)
        return _to_entity(record) if record else None

    async def create(self, rule: AutomationRule) -> AutomationRule:
        record = await AutomationTask.create(
            name=rule.name,
            event=rule.event,
            path_pattern=rule.path_pattern,
            filename_regex=rule.filename_regex,
            processor_type=rule.processor_type,
            processor_config=rule.processor_config,
            enabled=rule.enabled,
        )
        return _to_entity(record)

    async def update(self, task_id: int, updates: Dict) -> AutomationRule | None:
        record = await AutomationTask.get_or_none(id=task_id)
        if not record:
            return None
        for key, value in updates.items():
            setattr(record, key, value)
        await record.save()
        return _to_entity(record)

    async def delete(self, task_id: int) -> bool:
        deleted = await AutomationTask.filter(id=task_id).delete()
        return bool(deleted)


__all__ = ["TortoiseAutomationTaskRepository"]
