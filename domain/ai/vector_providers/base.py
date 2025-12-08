from __future__ import annotations

from typing import Any, Dict, List


class BaseVectorProvider:
    """向量数据库提供者基础类，所有实际实现需继承该类"""

    type: str = ""
    label: str = ""
    description: str | None = None
    enabled: bool = True
    config_schema: List[Dict[str, Any]] = []

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}

    async def initialize(self) -> None:
        """执行初始化逻辑，例如建立连接"""
        raise NotImplementedError

    def ensure_collection(self, collection_name: str, vector: bool, dim: int) -> None:
        raise NotImplementedError

    def upsert_vector(self, collection_name: str, data: Dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_vector(self, collection_name: str, path: str) -> None:
        raise NotImplementedError

    def search_vectors(self, collection_name: str, query_embedding, top_k: int):
        raise NotImplementedError

    def search_by_path(self, collection_name: str, query_path: str, top_k: int):
        raise NotImplementedError

    def get_all_stats(self) -> Dict[str, Any]:
        raise NotImplementedError

    def clear_all_data(self) -> None:
        raise NotImplementedError
