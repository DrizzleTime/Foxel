from fastapi import APIRouter, Depends, Query
from schemas.fs import SearchResultItem
from services.auth import get_current_active_user, User
from services.ai import get_text_embedding
from services.vector_db import VectorDBService

router = APIRouter(prefix="/api/search", tags=["search"])

async def search_files_by_vector(q: str, top_k: int):
    embedding = await get_text_embedding(q)
    vector_db = VectorDBService()
    results = await vector_db.search_vectors("vector_collection", embedding, top_k)
    items = [
        SearchResultItem(id=res["id"], path=res["entity"]["path"], score=res["distance"])
        for res in results[0]
    ]
    return {"items": items, "query": q}

async def search_files_by_name(q: str, top_k: int):
    vector_db = VectorDBService()
    results = await vector_db.search_by_path("vector_collection", q, top_k)
    items = [
        SearchResultItem(id=idx, path=res["entity"]["path"], score=res["distance"])
        for idx, res in enumerate(results[0])
    ]
    return {"items": items, "query": q}


@router.get("")
async def search_files(
    q: str = Query(..., description="搜索查询"),
    top_k: int = Query(10, description="返回结果数量"),
    mode: str = Query("vector", description="搜索模式: 'vector' 或 'filename'"),
    user: User = Depends(get_current_active_user),
):
    if mode == "vector":
        return await search_files_by_vector(q, top_k)
    elif mode == "filename":
        return await search_files_by_name(q, top_k)
    else:
        return {"items": [], "query": q, "error": "Invalid search mode"}
