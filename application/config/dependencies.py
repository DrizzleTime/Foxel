from __future__ import annotations

from application.config.use_cases import ConfigService
from infrastructure.persistence.config_repository import TortoiseConfigRepository

config_service = ConfigService(TortoiseConfigRepository())

__all__ = ["config_service"]
