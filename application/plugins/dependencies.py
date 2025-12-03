from __future__ import annotations

from application.plugins.use_cases import PluginService
from infrastructure.persistence.plugin_repository import TortoisePluginRepository

plugin_service = PluginService(TortoisePluginRepository())

__all__ = ["plugin_service"]
