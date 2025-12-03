from __future__ import annotations

from application.automation.use_cases import AutomationService
from infrastructure.processors import runtime_processor_registry
from infrastructure.persistence.automation_repository import (
    TortoiseAutomationTaskRepository,
)

_repository = TortoiseAutomationTaskRepository()
automation_service = AutomationService(
    repository=_repository, processor_registry=runtime_processor_registry
)

__all__ = ["automation_service"]
