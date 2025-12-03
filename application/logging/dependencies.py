from __future__ import annotations

from application.logging.use_cases import LoggingService
from infrastructure.persistence.log_repository import TortoiseLogRepository

logging_service = LoggingService(TortoiseLogRepository())

__all__ = ["logging_service"]
