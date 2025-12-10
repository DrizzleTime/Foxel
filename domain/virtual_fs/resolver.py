from typing import Tuple

from fastapi import HTTPException
from fastapi.responses import Response

from domain.adapters.registry import runtime_registry
from models import StorageAdapter

from .common import VirtualFSCommonMixin


class VirtualFSResolverMixin(VirtualFSCommonMixin):
    @classmethod
    async def resolve_adapter_by_path(cls, path: str) -> Tuple[StorageAdapter, str]:
        norm = cls._normalize_path(path)
        adapters = await StorageAdapter.filter(enabled=True)
        best = None
        for adapter in adapters:
            if norm == adapter.path or norm.startswith(adapter.path.rstrip("/") + "/"):
                if best is None or len(adapter.path) > len(best.path):
                    best = adapter
        if not best:
            raise HTTPException(404, detail="No storage adapter for path")
        rel = norm[len(best.path) :].lstrip("/")
        return best, rel

    @classmethod
    async def resolve_adapter_and_rel(cls, path: str):
        norm = cls._normalize_path(path)
        adapter_model, rel = await cls.resolve_adapter_by_path(norm)
        adapter_instance = runtime_registry.get(adapter_model.id)
        if not adapter_instance:
            await runtime_registry.refresh()
            adapter_instance = runtime_registry.get(adapter_model.id)
            if not adapter_instance:
                raise HTTPException(
                    404, detail=f"Adapter instance for ID {adapter_model.id} not found or failed to load."
                )
        effective_root = adapter_instance.get_effective_root(adapter_model.sub_path)
        return adapter_instance, adapter_model, effective_root, rel

    @classmethod
    async def maybe_redirect_download(cls, adapter_instance, adapter_model, root: str, rel: str):
        if not rel or rel.endswith("/"):
            return None

        config = getattr(adapter_model, "config", {}) or {}
        if not config.get(cls.DIRECT_REDIRECT_CONFIG_KEY):
            return None

        handler = getattr(adapter_instance, "get_direct_download_response", None)
        if not callable(handler):
            return None

        try:
            response = await handler(root, rel)
        except FileNotFoundError:
            raise
        except Exception:
            return None

        if isinstance(response, Response):
            return response
        return None
