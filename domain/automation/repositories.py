from __future__ import annotations

from typing import Dict, Protocol

from domain.automation.entities import AutomationRule


class AutomationTaskRepository(Protocol):
    async def list_all(self) -> list[AutomationRule]: ...

    async def list_enabled_by_event(self, event: str) -> list[AutomationRule]: ...

    async def get(self, task_id: int) -> AutomationRule | None: ...

    async def create(self, rule: AutomationRule) -> AutomationRule: ...

    async def update(self, task_id: int, updates: Dict) -> AutomationRule | None: ...

    async def delete(self, task_id: int) -> bool: ...


__all__ = ["AutomationTaskRepository"]
