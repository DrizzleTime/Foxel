from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from .base import BaseVectorProvider


class QdrantProvider(BaseVectorProvider):
    type = "qdrant"
    label = "Qdrant"
    description = "Qdrant vector database (HTTP API)."
    enabled = True
    config_schema: List[Dict[str, Any]] = [
        {
            "key": "url",
            "label": "Server URL",
            "type": "text",
            "required": True,
            "placeholder": "http://localhost:6333",
        },
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "required": False,
        },
    ]

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(config)
        self.client: Optional[QdrantClient] = None

    async def initialize(self) -> None:
        url = (self.config.get("url") or "").strip()
        if not url:
            raise RuntimeError("Qdrant URL is required")

        api_key = (self.config.get("api_key") or None) or None
        try:
            client = QdrantClient(url=url, api_key=api_key)
            # 简单连通性校验
            client.get_collections()
            self.client = client
        except Exception as exc:  # pragma: no cover - 依赖外部服务
            raise RuntimeError(f"Failed to connect to Qdrant at {url}: {exc}") from exc

    def _get_client(self) -> QdrantClient:
        if not self.client:
            raise RuntimeError("Qdrant client is not initialized")
        return self.client

    @staticmethod
    def _vector_params(vector: bool, dim: int) -> qmodels.VectorParams:
        size = dim if vector and isinstance(dim, int) and dim > 0 else 1
        return qmodels.VectorParams(size=size, distance=qmodels.Distance.COSINE)

    def _ensure_payload_indexes(self, client: QdrantClient, collection_name: str) -> None:
        for field in ("path", "source_path"):
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema="keyword",
                )
            except Exception as exc:  # pragma: no cover - 依赖外部服务
                message = str(exc).lower()
                if "already exists" in message or "index exists" in message:
                    continue
                # 旧版本 qdrant 可能返回带状态码的异常，这里容忍重复创建
                raise

    def ensure_collection(self, collection_name: str, vector: bool, dim: int) -> None:
        client = self._get_client()
        try:
            exists = client.collection_exists(collection_name)
        except Exception as exc:  # pragma: no cover - 依赖外部服务
            raise RuntimeError(f"Failed to check Qdrant collection '{collection_name}': {exc}") from exc

        if exists:
            try:
                self._ensure_payload_indexes(client, collection_name)
            except Exception:
                pass
            return

        vectors_config = self._vector_params(vector, dim)
        try:
            client.create_collection(collection_name=collection_name, vectors_config=vectors_config)
        except Exception as exc:  # pragma: no cover
            if "already exists" in str(exc).lower():
                try:
                    self._ensure_payload_indexes(client, collection_name)
                except Exception:
                    pass
                return
            raise RuntimeError(f"Failed to create Qdrant collection '{collection_name}': {exc}") from exc

        try:
            self._ensure_payload_indexes(client, collection_name)
        except Exception:
            pass

    @staticmethod
    def _point_id(uid: str) -> str:
        return str(uuid5(NAMESPACE_URL, uid))

    def _prepare_point(self, data: Dict[str, Any]) -> qmodels.PointStruct:
        uid = data.get("path")
        if not uid:
            raise ValueError("Qdrant upsert requires 'path' in data")

        embedding = data.get("embedding")
        if embedding is None:
            vector = [0.0]
        else:
            vector = [float(x) for x in embedding]

        payload = {k: v for k, v in data.items() if k != "embedding"}
        payload.setdefault("vector_id", uid)
        source_path = payload.get("source_path") or payload.get("path")
        payload["path"] = source_path
        return qmodels.PointStruct(id=self._point_id(str(uid)), vector=vector, payload=payload)

    def upsert_vector(self, collection_name: str, data: Dict[str, Any]) -> None:
        client = self._get_client()
        point = self._prepare_point(data)
        client.upsert(collection_name=collection_name, wait=True, points=[point])

    def delete_vector(self, collection_name: str, path: str) -> None:
        client = self._get_client()
        condition = qmodels.FieldCondition(
            key="path",
            match=qmodels.MatchValue(value=path),
        )
        flt = qmodels.Filter(must=[condition])
        selector = qmodels.FilterSelector(filter=flt)
        client.delete(collection_name=collection_name, points_selector=selector, wait=True)

    def _format_search_results(self, points: Sequence[qmodels.ScoredPoint]):
        return [
            {
                "id": point.id,
                "distance": point.score,
                "entity": point.payload or {},
            }
            for point in points
        ]

    def search_vectors(self, collection_name: str, query_embedding, top_k: int):
        client = self._get_client()
        vector = [float(x) for x in query_embedding]
        points = client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )
        return [self._format_search_results(points)]

    def search_by_path(self, collection_name: str, query_path: str, top_k: int):
        client = self._get_client()
        results: List[Dict[str, Any]] = []
        offset: Optional[str | int] = None
        remaining = max(top_k, 1)

        while len(results) < top_k:
            batch_size = min(max(remaining * 2, 10), 200)
            records, next_offset = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
            )
            if not records:
                break

            for record in records:
                payload = record.payload or {}
                path = payload.get("path")
                if query_path and path and query_path not in path:
                    continue
                results.append({"id": record.id, "distance": 1.0, "entity": payload})
                if len(results) >= top_k:
                    break

            if next_offset is None or len(results) >= top_k:
                break
            offset = next_offset
            remaining = top_k - len(results)

        return [results]

    def _extract_vector_config(self, vectors) -> Optional[qmodels.VectorParams]:
        if isinstance(vectors, qmodels.VectorParams):
            return vectors
        if isinstance(vectors, dict):
            for value in vectors.values():
                if isinstance(value, qmodels.VectorParams):
                    return value
        return None

    def get_all_stats(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            response = client.get_collections()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to list Qdrant collections: {exc}") from exc

        collections: List[Dict[str, Any]] = []
        total_vectors = 0
        total_estimated_memory = 0

        for description in response.collections or []:
            name = description.name
            try:
                info = client.get_collection(name)
            except Exception:
                continue

            row_count = int(info.points_count or 0)
            total_vectors += row_count

            vector_params = self._extract_vector_config(info.config.params.vectors if info.config and info.config.params else None)
            dimension = int(vector_params.size) if vector_params and vector_params.size else None
            estimated_memory = row_count * dimension * 4 if dimension else 0
            total_estimated_memory += estimated_memory
            distance = str(vector_params.distance) if vector_params and vector_params.distance else None

            indexed_rows = int(info.indexed_vectors_count or 0)
            pending_rows = max(row_count - indexed_rows, 0)

            collections.append(
                {
                    "name": name,
                    "row_count": row_count,
                    "dimension": dimension,
                    "estimated_memory_bytes": estimated_memory,
                    "is_vector_collection": dimension is not None and dimension > 1,
                    "indexes": [
                        {
                            "index_name": "hnsw",
                            "index_type": "HNSW",
                            "metric_type": distance,
                            "indexed_rows": indexed_rows,
                            "pending_index_rows": pending_rows,
                            "state": info.status,
                        }
                    ],
                }
            )

        return {
            "collections": collections,
            "collection_count": len(collections),
            "total_vectors": total_vectors,
            "estimated_total_memory_bytes": total_estimated_memory,
            "db_file_size_bytes": None,
        }

    def clear_all_data(self) -> None:
        client = self._get_client()
        try:
            response = client.get_collections()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to list Qdrant collections: {exc}") from exc

        for description in response.collections or []:
            try:
                client.delete_collection(description.name)
            except Exception:
                continue
