from typing import Optional

from fastapi import HTTPException

from domain.auth import User
from .registry import (
    get_config_schemas,
    normalize_adapter_type,
    runtime_registry,
)
from .types import AdapterCreate, AdapterOut
from models import StorageAdapter


class AdapterService:
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
        return AdapterOut.model_validate(rec)

    @classmethod
    async def delete_adapter(cls, adapter_id: int, current_user: Optional[User]):
        deleted = await StorageAdapter.filter(id=adapter_id).delete()
        if not deleted:
            raise HTTPException(404, detail="Not found")
        runtime_registry.remove(adapter_id)
        return {"deleted": True}
