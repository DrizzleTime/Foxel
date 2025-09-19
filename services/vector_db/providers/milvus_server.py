from __future__ import annotations

from typing import Any, Dict, List, Optional

from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient

from .base import BaseVectorProvider


class MilvusServerProvider(BaseVectorProvider):
    type = "milvus_server"
    label = "Milvus Server"
    description = "Remote Milvus instance accessed via URI."
    enabled = True
    config_schema: List[Dict[str, Any]] = [
        {
            "key": "uri",
            "label": "Server URI",
            "type": "text",
            "required": True,
            "placeholder": "http://localhost:19530",
        },
        {
            "key": "token",
            "label": "Token",
            "type": "password",
            "required": False,
            "placeholder": "user:password",
        },
    ]

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(config)
        self.client: MilvusClient | None = None

    async def initialize(self) -> None:
        uri = self.config.get("uri")
        if not uri:
            raise RuntimeError("Milvus Server URI is required")
        try:
            self.client = MilvusClient(uri=uri, token=self.config.get("token"))
        except Exception as exc:  # pragma: no cover - depends on remote availability
            raise RuntimeError(f"Failed to connect to Milvus Server {uri}: {exc}") from exc

    def _get_client(self) -> MilvusClient:
        if not self.client:
            raise RuntimeError("Milvus Server client is not initialized")
        return self.client

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def ensure_collection(self, collection_name: str, vector: bool, dim: int) -> None:
        client = self._get_client()
        if client.has_collection(collection_name):
            return
        if vector:
            vector_dim = dim if isinstance(dim, int) and dim > 0 else 0
            if vector_dim <= 0:
                vector_dim = 4096
            fields = [
                FieldSchema(name="path", dtype=DataType.VARCHAR, max_length=512, is_primary=True, auto_id=False),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=vector_dim),
            ]
            schema = CollectionSchema(fields, description="Image vector collection")
            client.create_collection(collection_name, schema=schema)
            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                index_type="IVF_FLAT",
                index_name="vector_index",
                metric_type="COSINE",
                params={"nlist": 64},
            )
            client.create_index(collection_name, index_params=index_params)
        else:
            fields = [
                FieldSchema(name="path", dtype=DataType.VARCHAR, max_length=512, is_primary=True, auto_id=False),
            ]
            schema = CollectionSchema(fields, description="Simple file index")
            client.create_collection(collection_name, schema=schema)

    def upsert_vector(self, collection_name: str, data: Dict[str, Any]) -> None:
        self._get_client().upsert(collection_name, data)

    def delete_vector(self, collection_name: str, path: str) -> None:
        self._get_client().delete(collection_name, ids=[path])

    def search_vectors(self, collection_name: str, query_embedding, top_k: int):
        search_params = {"metric_type": "COSINE"}
        return self._get_client().search(
            collection_name,
            data=[query_embedding],
            anns_field="embedding",
            search_params=search_params,
            limit=top_k,
            output_fields=["path"],
        )

    def search_by_path(self, collection_name: str, query_path: str, top_k: int):
        filter_expr = f"path like '%{query_path}%'" if query_path else "path like '%%'"
        results = self._get_client().query(
            collection_name,
            filter=filter_expr,
            limit=top_k,
            output_fields=["path"],
        )
        return [[{"id": r["path"], "distance": 1.0, "entity": {"path": r["path"]}} for r in results]]

    def get_all_stats(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            collection_names = client.list_collections()
        except Exception as exc:
            raise RuntimeError(f"Failed to list collections: {exc}") from exc

        collections: List[Dict[str, Any]] = []
        total_vectors = 0
        total_estimated_memory = 0

        for name in collection_names:
            try:
                stats = client.get_collection_stats(name) or {}
            except Exception:
                stats = {}
            row_count = self._to_int(stats.get("row_count"))
            total_vectors += row_count

            dimension: Optional[int] = None
            is_vector_collection = False
            try:
                description = client.describe_collection(name)
            except Exception:
                description = None

            if description:
                for field in description.get("fields", []):
                    if field.get("type") == DataType.FLOAT_VECTOR:
                        params = field.get("params") or {}
                        dimension = self._to_int(params.get("dim")) or 4096
                        is_vector_collection = True
                        break

            estimated_memory = 0
            if is_vector_collection and dimension:
                estimated_memory = row_count * dimension * 4
                total_estimated_memory += estimated_memory

            indexes: List[Dict[str, Any]] = []
            try:
                index_names = client.list_indexes(name) or []
            except Exception:
                index_names = []

            for index_name in index_names:
                try:
                    detail = client.describe_index(name, index_name) or {}
                except Exception:
                    detail = {}
                indexes.append(
                    {
                        "index_name": index_name,
                        "index_type": detail.get("index_type"),
                        "metric_type": detail.get("metric_type"),
                        "indexed_rows": self._to_int(detail.get("indexed_rows")),
                        "pending_index_rows": self._to_int(detail.get("pending_index_rows")),
                        "state": detail.get("state"),
                    }
                )

            collections.append(
                {
                    "name": name,
                    "row_count": row_count,
                    "dimension": dimension if is_vector_collection else None,
                    "estimated_memory_bytes": estimated_memory,
                    "is_vector_collection": is_vector_collection,
                    "indexes": indexes,
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
        for collection_name in client.list_collections():
            client.drop_collection(collection_name)
