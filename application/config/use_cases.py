from __future__ import annotations

import os
from typing import Any, Dict, Optional

from domain.config.repositories import ConfigRepository


class ConfigService:
    def __init__(self, repository: ConfigRepository, env_reader=os.getenv):
        self._repository = repository
        self._env_reader = env_reader
        self._cache: Dict[str, Any] = {}

    async def get(self, key: str, default: Optional[Any] = None) -> Any:
        if key in self._cache:
            return self._cache[key]
        value = await self._repository.get(key)
        if value is not None:
            self._cache[key] = value
            return value
        env_value = self._env_reader(key)
        if env_value is not None:
            self._cache[key] = env_value
            return env_value
        return default

    async def get_secret_key(self, key: str, default: Optional[Any] = None) -> bytes:
        value = await self.get(key, default)
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        if value is None:
            raise ValueError(f"Secret key '{key}' not found in config or environment.")
        return str(value).encode("utf-8")

    async def set(self, key: str, value: Any):
        await self._repository.set(key, value)
        self._cache[key] = value

    async def get_all(self) -> Dict[str, Any]:
        configs = await self._repository.get_all()
        self._cache.update(configs)
        return configs

    def clear_cache(self):
        self._cache.clear()


__all__ = ["ConfigService"]
