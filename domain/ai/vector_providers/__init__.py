from typing import Dict, List, Type

from .base import BaseVectorProvider
from .milvus_lite import MilvusLiteProvider
from .milvus_server import MilvusServerProvider
from .qdrant import QdrantProvider

_PROVIDER_REGISTRY: Dict[str, Dict[str, object]] = {
    MilvusLiteProvider.type: {
        "class": MilvusLiteProvider,
        "label": MilvusLiteProvider.label,
        "description": MilvusLiteProvider.description,
        "enabled": MilvusLiteProvider.enabled,
        "config_schema": MilvusLiteProvider.config_schema,
    },
    MilvusServerProvider.type: {
        "class": MilvusServerProvider,
        "label": MilvusServerProvider.label,
        "description": MilvusServerProvider.description,
        "enabled": MilvusServerProvider.enabled,
        "config_schema": MilvusServerProvider.config_schema,
    },
    QdrantProvider.type: {
        "class": QdrantProvider,
        "label": QdrantProvider.label,
        "description": QdrantProvider.description,
        "enabled": QdrantProvider.enabled,
        "config_schema": QdrantProvider.config_schema,
    },
}


def list_providers() -> List[Dict[str, object]]:
    return [
        {
            "type": type_key,
            "label": meta["label"],
            "description": meta.get("description"),
            "enabled": meta.get("enabled", True),
            "config_schema": meta.get("config_schema", []),
        }
        for type_key, meta in _PROVIDER_REGISTRY.items()
    ]


def get_provider_entry(provider_type: str) -> Dict[str, object] | None:
    return _PROVIDER_REGISTRY.get(provider_type)


def get_provider_class(provider_type: str) -> Type[BaseVectorProvider] | None:
    entry = get_provider_entry(provider_type)
    if not entry:
        return None
    return entry.get("class")  # type: ignore[return-value]


__all__ = [
    "BaseVectorProvider",
    "MilvusLiteProvider",
    "MilvusServerProvider",
    "QdrantProvider",
    "list_providers",
    "get_provider_entry",
    "get_provider_class",
]
