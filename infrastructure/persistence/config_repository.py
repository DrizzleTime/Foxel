from __future__ import annotations

from typing import Any, Dict

from domain.config.repositories import ConfigRepository
from models.database import Configuration


class TortoiseConfigRepository(ConfigRepository):
    async def get(self, key: str) -> Any | None:
        rec = await Configuration.get_or_none(key=key)
        return rec.value if rec else None

    async def set(self, key: str, value: Any) -> None:
        obj, _ = await Configuration.get_or_create(key=key, defaults={"value": value})
        obj.value = value
        await obj.save()

    async def get_all(self) -> Dict[str, Any]:
        records = await Configuration.all()
        return {rec.key: rec.value for rec in records}

    async def delete(self, key: str) -> bool:
        deleted = await Configuration.filter(key=key).delete()
        return bool(deleted)


__all__ = ["TortoiseConfigRepository"]
