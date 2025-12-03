from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Optional

from domain.storage.entities import StorageMount
from domain.storage.repositories import StorageMountRepository
from infrastructure.storage_adapters.registry import get_config_schemas, normalize_adapter_type
from infrastructure.storage_adapters.runtime_registry import RuntimeStorageGatewayRegistry
from schemas.adapters import AdapterCreate


def _validate_and_normalize_config(adapter_type: str, cfg: Dict) -> Dict:
    schemas = get_config_schemas()
    adapter_type = normalize_adapter_type(adapter_type)
    if not adapter_type:
        raise ValueError("不支持的适配器类型")
    if not isinstance(cfg, dict):
        raise ValueError("config 必须是对象")
    schema = schemas.get(adapter_type)
    if not schema:
        raise ValueError(f"不支持的适配器类型: {adapter_type}")
    out = {}
    missing = []
    for f in schema:
        k = f["key"]
        if k in cfg and cfg[k] not in (None, ""):
            out[k] = cfg[k]
        elif "default" in f:
            out[k] = f["default"]
        elif f.get("required"):
            missing.append(k)
    if missing:
        raise ValueError("缺少必填配置字段: " + ", ".join(missing))
    return out


class AdapterService:
    def __init__(
        self,
        repository: StorageMountRepository,
        registry: RuntimeStorageGatewayRegistry,
    ):
        self._repository = repository
        self._registry = registry

    async def list_adapters(self) -> List[StorageMount]:
        return await self._repository.list_all()

    async def get_adapter(self, adapter_id: int) -> StorageMount | None:
        return await self._repository.get_by_id(adapter_id)

    async def create_adapter(self, payload: Dict) -> StorageMount:
        norm_path = AdapterCreate.normalize_mount_path(payload["path"])
        exists = await self._repository.get_by_path(norm_path)
        if exists:
            raise ValueError("Mount path already exists")

        config = _validate_and_normalize_config(
            payload["type"], payload.get("config") or {}
        )

        mount = StorageMount(
            id=0,
            name=payload["name"],
            type=normalize_adapter_type(payload["type"]),
            config=config,
            enabled=payload.get("enabled", True),
            path=norm_path,
            sub_path=payload.get("sub_path"),
        )
        created = await self._repository.create(mount)
        await self._registry.upsert(_AdapterRecordProxy(created))
        return created

    async def update_adapter(self, adapter_id: int, payload: Dict) -> StorageMount:
        norm_path = AdapterCreate.normalize_mount_path(payload["path"])
        existing = await self._repository.get_by_path(norm_path)
        if existing and existing.id != adapter_id:
            raise ValueError("Mount path already exists")

        config = _validate_and_normalize_config(
            payload["type"], payload.get("config") or {}
        )

        mount = StorageMount(
            id=adapter_id,
            name=payload["name"],
            type=normalize_adapter_type(payload["type"]),
            config=config,
            enabled=payload.get("enabled", True),
            path=norm_path,
            sub_path=payload.get("sub_path"),
        )
        updated = await self._repository.update(adapter_id, mount)
        if not updated:
            raise ValueError("Not found")
        await self._registry.upsert(_AdapterRecordProxy(updated))
        return updated

    async def delete_adapter(self, adapter_id: int) -> bool:
        deleted = await self._repository.delete(adapter_id)
        if deleted:
            self._registry.remove(adapter_id)
        return deleted

    def available_adapter_types(self) -> List[Dict]:
        data = []
        for t, fields in get_config_schemas().items():
            data.append({"type": t, "config_schema": fields})
        return data


class _AdapterRecordProxy:
    """简易代理以适配 legacy runtime_registry.upsert 所需字段。"""

    def __init__(self, mount: StorageMount):
        self.id = mount.id
        self.name = mount.name
        self.type = mount.type
        self.config = mount.config
        self.enabled = mount.enabled
        self.path = mount.path
        self.sub_path = mount.sub_path


__all__ = ["AdapterService"]
