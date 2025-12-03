from __future__ import annotations

from typing import Any, Dict, Protocol


class ConfigRepository(Protocol):
    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any) -> None: ...

    async def get_all(self) -> Dict[str, Any]: ...

    async def delete(self, key: str) -> bool: ...


__all__ = ["ConfigRepository"]
