from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from .config_manager import VectorDBConfigManager
from .providers import get_provider_class, get_provider_entry
from .providers.base import BaseVectorProvider

DEFAULT_VECTOR_DIMENSION = 4096


class VectorDBService:
    _instance: "VectorDBService" | None = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_provider"):
            self._provider: Optional[BaseVectorProvider] = None
            self._provider_type: Optional[str] = None
            self._provider_config: Dict[str, Any] | None = None
            self._lock = asyncio.Lock()

    async def _ensure_provider(self) -> BaseVectorProvider:
        if self._provider is None:
            await self.reload()
        assert self._provider is not None  # for type checker
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
