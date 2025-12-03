"""兼容层：向量库逻辑迁至 application.vector_db.use_cases。"""

from application.vector_db.dependencies import vector_db_use_cases
from application.vector_db.use_cases import DEFAULT_VECTOR_DIMENSION


class VectorDBService:
    async def ensure_collection(self, collection_name: str, vector: bool = True, dim: int = DEFAULT_VECTOR_DIMENSION) -> None:
        await vector_db_use_cases.ensure_collection(collection_name, vector, dim)

    async def upsert_vector(self, collection_name: str, data):
        await vector_db_use_cases.upsert_vector(collection_name, data)

    async def delete_vector(self, collection_name: str, path: str):
        await vector_db_use_cases.delete_vector(collection_name, path)

    async def search_vectors(self, collection_name: str, query_embedding, top_k: int = 5):
        return await vector_db_use_cases.search_vectors(collection_name, query_embedding, top_k)

    async def search_by_path(self, collection_name: str, query_path: str, top_k: int = 20):
        return await vector_db_use_cases.search_by_path(collection_name, query_path, top_k)

    async def get_all_stats(self):
        return await vector_db_use_cases.get_all_stats()

    async def clear_all_data(self):
        await vector_db_use_cases.clear_all_data()

    async def current_provider(self):
        return await vector_db_use_cases.current_provider()

    async def reload(self):
        return await vector_db_use_cases.reload()
