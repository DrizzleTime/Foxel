from __future__ import annotations

from application.processors.use_cases import ProcessorService
from infrastructure.processors import runtime_processor_registry

processor_service = ProcessorService(runtime_processor_registry)

__all__ = ["processor_service"]
