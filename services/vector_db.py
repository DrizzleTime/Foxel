from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient


DEFAULT_VECTOR_DIMENSION = 4096


class VectorDBService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VectorDBService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'client'):
            self.client = MilvusClient("data/db/milvus.db")

    def ensure_collection(self, collection_name, vector: bool = True, dim: int = DEFAULT_VECTOR_DIMENSION):
        if self.client.has_collection(collection_name):
            return
        if vector:
            try:
                vector_dim = int(dim)
            except (TypeError, ValueError):
                vector_dim = DEFAULT_VECTOR_DIMENSION
            if vector_dim <= 0:
                vector_dim = DEFAULT_VECTOR_DIMENSION
            fields = [
                FieldSchema(name="path", dtype=DataType.VARCHAR,
                            max_length=512, is_primary=True, auto_id=False),
                FieldSchema(name="embedding",
                            dtype=DataType.FLOAT_VECTOR, dim=vector_dim)
            ]
            schema = CollectionSchema(
                fields, description="Image vector collection")
            self.client.create_collection(collection_name, schema=schema)
            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                index_type="IVF_FLAT",
                index_name="vector_index",
                metric_type="COSINE",
                params={
                    "nlist": 64,
                }
            )
            self.client.create_index(
                collection_name,
                index_params=index_params
            )
        else:
            fields = [
                FieldSchema(name="path", dtype=DataType.VARCHAR,
                            max_length=512, is_primary=True, auto_id=False),
            ]
            schema = CollectionSchema(fields, description="Simple file index")
            self.client.create_collection(collection_name, schema=schema)

    def upsert_vector(self, collection_name, data):
        self.client.upsert(collection_name, data)

    def delete_vector(self, collection_name, path: str):
        self.client.delete(collection_name, ids=[path])

    def search_vectors(self, collection_name, query_embedding, top_k=5):
        search_params = {"metric_type": "COSINE"}
        results = self.client.search(
            collection_name,
            data=[query_embedding],
            anns_field="embedding",
            search_params=search_params,
            limit=top_k,
            output_fields=["path"]
        )
        print(results)
        return results

    def search_by_path(self, collection_name, query_path, top_k=20):
        results = self.client.query(
            collection_name,
            filter=f"path like '%{query_path}%'",
            limit=top_k,
            output_fields=["path"]
        )
        return [[{'id': r['path'], 'distance': 1.0, 'entity': {'path': r['path']}} for r in results]]

    def clear_all_data(self):
        """清空所有集合的内容"""
        collections = self.client.list_collections()
        for collection_name in collections:
            self.client.drop_collection(collection_name)
