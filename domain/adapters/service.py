import time
from typing import Optional

from fastapi import HTTPException

from domain.auth import User
from .registry import (
    get_config_schemas,
    normalize_adapter_type,
    runtime_registry,
)
from .types import AdapterCreate, AdapterOut, AdapterUsage
from .providers.base import UsageCapableAdapter
from models import StorageAdapter


class AdapterService:
    _usage_cache_ttl = 3600
    _usage_cache: dict[int, tuple[float, AdapterUsage]] = {}

    @classmethod
    def _get_cached_usage(cls, adapter_id: int) -> AdapterUsage | None:
        cached = cls._usage_cache.get(adapter_id)
        if not cached:
            return None
        expires_at, usage = cached
        if expires_at <= time.time():
            cls._usage_cache.pop(adapter_id, None)
            return None
        return usage

    @classmethod
    def _set_cached_usage(cls, usage: AdapterUsage):
        cls._usage_cache[usage.id] = (time.time() + cls._usage_cache_ttl, usage)

    @classmethod
    def _clear_cached_usage(cls, adapter_id: int):
        cls._usage_cache.pop(adapter_id, None)

    @classmethod
    def _validate_and_normalize_config(cls, adapter_type: str, cfg):
        schemas = get_config_schemas()
        adapter_type = normalize_adapter_type(adapter_type)
        if not adapter_type:
            raise HTTPException(400, detail="不支持的适配器类型")
        if not isinstance(cfg, dict):
            raise HTTPException(400, detail="config 必须是对象")
        schema = schemas.get(adapter_type)
        if not schema:
            raise HTTPException(400, detail=f"不支持的适配器类型: {adapter_type}")
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
            raise HTTPException(400, detail="缺少必填配置字段: " + ", ".join(missing))
        if adapter_type in ("alist", "openlist"):
            username = out.get("username")
            password = out.get("password")
            if (username and not password) or (password and not username):
                raise HTTPException(400, detail="用户名和密码必须同时填写或同时留空")
        return out

    @classmethod
    async def create_adapter(cls, data: AdapterCreate, current_user: Optional[User]):
        norm_path = AdapterCreate.normalize_mount_path(data.path)
        exists = await StorageAdapter.get_or_none(path=norm_path)
        if exists:
            raise HTTPException(400, detail="Mount path already exists")

        adapter_fields = {
            "name": data.name,
            "type": data.type,
            "config": cls._validate_and_normalize_config(data.type, data.config or {}),
            "enabled": data.enabled,
            "path": norm_path,
            "sub_path": data.sub_path,
        }

        rec = await StorageAdapter.create(**adapter_fields)
        await runtime_registry.upsert(rec)
        return AdapterOut.model_validate(rec)

    @classmethod
    async def list_adapters(cls):
        adapters = await StorageAdapter.all()
        return [AdapterOut.model_validate(a) for a in adapters]

    @classmethod
    async def available_adapter_types(cls):
        data = []
        for adapter_type, fields in get_config_schemas().items():
            data.append({
                "type": adapter_type,
                "config_schema": fields,
            })
        return data

    @classmethod
    async def get_adapter(cls, adapter_id: int):
        rec = await StorageAdapter.get_or_none(id=adapter_id)
        if not rec:
            raise HTTPException(404, detail="Not found")
        return AdapterOut.model_validate(rec)

    @classmethod
    def _unsupported_usage(cls, rec: StorageAdapter, reason: str) -> AdapterUsage:
        return AdapterUsage(
            id=rec.id,
            name=rec.name,
            type=rec.type,
            path=rec.path,
            supported=False,
            reason=reason,
        )

    @classmethod
    async def get_adapter_usage(cls, adapter_id: int) -> AdapterUsage:
        rec = await StorageAdapter.get_or_none(id=adapter_id)
        if not rec:
            raise HTTPException(404, detail="Not found")
        return await cls._get_adapter_usage_for_record(rec)

    @classmethod
    async def _get_adapter_usage_for_record(cls, rec: StorageAdapter) -> AdapterUsage:
        cached = cls._get_cached_usage(rec.id)
        if cached:
            return cached

        if not rec.enabled:
            return cls._unsupported_usage(rec, "adapter_disabled")

        adapter = runtime_registry.get(rec.id)
        if not adapter:
            await runtime_registry.refresh()
            adapter = runtime_registry.get(rec.id)
        if not adapter:
            return cls._unsupported_usage(rec, "adapter_unavailable")
        if not isinstance(adapter, UsageCapableAdapter):
            return cls._unsupported_usage(rec, "adapter_not_implemented")

        root = adapter.get_effective_root(rec.sub_path)
        try:
            raw_usage = await adapter.get_usage(root)
        except Exception as e:
            return cls._unsupported_usage(rec, f"usage_failed: {e}")

        if not isinstance(raw_usage, dict):
            return cls._unsupported_usage(rec, "invalid_usage_response")

        usage = AdapterUsage(
            id=rec.id,
            name=rec.name,
            type=rec.type,
            path=rec.path,
            supported=True,
            used_bytes=raw_usage.get("used_bytes"),
            total_bytes=raw_usage.get("total_bytes"),
            free_bytes=raw_usage.get("free_bytes"),
            source=raw_usage.get("source") or rec.type,
            scope=raw_usage.get("scope"),
        )
        cls._set_cached_usage(usage)
        return usage

    @classmethod
    async def list_adapter_usages(cls):
        adapters = await StorageAdapter.all()
        result = []
        for rec in adapters:
            result.append(await cls._get_adapter_usage_for_record(rec))
        return result

    @classmethod
    async def update_adapter(cls, adapter_id: int, data: AdapterCreate, current_user: Optional[User]):
        rec = await StorageAdapter.get_or_none(id=adapter_id)
        if not rec:
            raise HTTPException(404, detail="Not found")

        norm_path = AdapterCreate.normalize_mount_path(data.path)
        existing = await StorageAdapter.get_or_none(path=norm_path)
        if existing and existing.id != adapter_id:
            raise HTTPException(400, detail="Mount path already exists")

        rec.name = data.name
        rec.type = data.type
        rec.config = cls._validate_and_normalize_config(data.type, data.config or {})
        rec.enabled = data.enabled
        rec.path = norm_path
        rec.sub_path = data.sub_path
        await rec.save()

        await runtime_registry.upsert(rec)
        cls._clear_cached_usage(adapter_id)
        return AdapterOut.model_validate(rec)

    @classmethod
    async def delete_adapter(cls, adapter_id: int, current_user: Optional[User]):
        deleted = await StorageAdapter.filter(id=adapter_id).delete()
        if not deleted:
            raise HTTPException(404, detail="Not found")
        runtime_registry.remove(adapter_id)
        cls._clear_cached_usage(adapter_id)
        return {"deleted": True}
