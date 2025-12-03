from __future__ import annotations

import asyncio
from typing import Any, Dict

from infrastructure.vector_db.config_manager import VectorDBConfigManager
from infrastructure.vector_db.providers import (
    get_provider_class,
    get_provider_entry,
    list_providers,
)
from infrastructure.vector_db.providers.base import BaseVectorProvider

DEFAULT_VECTOR_DIMENSION = 4096


class VectorDBUseCases:
    def __init__(self):
        self._provider: BaseVectorProvider | None = None
        self._provider_type: str | None = None
        self._provider_config: Dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def _ensure_provider(self) -> BaseVectorProvider:
        if self._provider is None:
            await self.reload()
        assert self._provider is not None
        return self._provider

    async def reload(self) -> BaseVectorProvider:
        async with self._lock:
            provider_type, provider_config = await VectorDBConfigManager.load_config()
            normalized_config = dict(provider_config or {})
            if (
                self._provider
                and self._provider_type == provider_type
                and self._provider_config == normalized_config
            ):
                return self._provider

            entry = get_provider_entry(provider_type)
            if not entry:
                raise RuntimeError(f"Unknown vector database provider: {provider_type}")
            if not entry.get("enabled", True):
                raise RuntimeError(f"Vector database provider '{provider_type}' is disabled")

            provider_cls = get_provider_class(provider_type)
            if not provider_cls:
                raise RuntimeError(f"Provider class not found for '{provider_type}'")

            provider = provider_cls(provider_config)
            await provider.initialize()

            self._provider = provider
            self._provider_type = provider_type
            self._provider_config = normalized_config
            return provider

    async def ensure_collection(self, collection_name: str, vector: bool = True, dim: int = DEFAULT_VECTOR_DIMENSION) -> None:
        provider = await self._ensure_provider()
        provider.ensure_collection(collection_name, vector, dim)

    async def upsert_vector(self, collection_name: str, data: Dict[str, Any]) -> None:
        provider = await self._ensure_provider()
        provider.upsert_vector(collection_name, data)

    async def delete_vector(self, collection_name: str, path: str) -> None:
        provider = await self._ensure_provider()
        provider.delete_vector(collection_name, path)

    async def search_vectors(self, collection_name: str, query_embedding, top_k: int = 5):
        provider = await self._ensure_provider()
        return provider.search_vectors(collection_name, query_embedding, top_k)

    async def search_by_path(self, collection_name: str, query_path: str, top_k: int = 20):
        provider = await self._ensure_provider()
        return provider.search_by_path(collection_name, query_path, top_k)

    async def get_all_stats(self) -> Dict[str, Any]:
        provider = await self._ensure_provider()
        return provider.get_all_stats()

    async def clear_all_data(self) -> None:
        provider = await self._ensure_provider()
        provider.clear_all_data()

    async def current_provider(self) -> Dict[str, Any]:
        provider_type, provider_config = await VectorDBConfigManager.load_config()
        entry = get_provider_entry(provider_type) or {}
        return {
            "type": provider_type,
            "config": provider_config,
            "label": entry.get("label"),
            "enabled": entry.get("enabled", True),
        }

    async def list_providers(self):
        return list_providers()

    async def update_config(self, provider_type: str, config: Dict[str, Any]):
        entry = get_provider_entry(provider_type)
        if not entry:
            raise ValueError(f"未知的向量数据库类型: {provider_type}")
        if not entry.get("enabled", True):
            raise ValueError("该向量数据库类型暂不可用")

        provider_cls = get_provider_class(provider_type)
        if not provider_cls:
            raise ValueError(f"未找到类型 {provider_type} 对应的实现")

        test_provider = provider_cls(config)
        client = getattr(test_provider, "client", None)
        try:
            await test_provider.initialize()
        except Exception as exc:  # noqa: BLE001
            raise ValueError(str(exc)) from exc
        finally:
            close_fn = getattr(client, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass

        await VectorDBConfigManager.save_config(provider_type, config)
        await self.reload()


__all__ = ["VectorDBUseCases", "DEFAULT_VECTOR_DIMENSION"]
