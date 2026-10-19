from fastapi import APIRouter, Depends, Query

from api.response import success
from domain.auth import User, get_current_active_user
from domain.permission.service import PermissionService
from domain.permission.types import PathAction
from .search_service import VirtualFSSearchService

router = APIRouter(prefix="/api/fs/search", tags=["search"])


@router.get("")
async def search_files(
    q: str = Query(..., description="搜索查询"),
    top_k: int = Query(10, description="返回结果数量"),
    mode: str = Query("hybrid", description="已忽略，始终用 BM25 与向量做 RRF 融合"),
    page: int = Query(1, description="已忽略"),
    page_size: int = Query(10, description="已忽略"),
    user: User = Depends(get_current_active_user),
):
    if not q.strip():
        return success({"items": [], "query": q, "mode": "hybrid"})

    top_k = max(top_k, 1)
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)

    data = await VirtualFSSearchService.search(q, top_k, mode, page, page_size)
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list) and items:
        path_pairs = [(str(item.path), item) for item in items if getattr(item, "path", None)]
        allowed_paths = await PermissionService.filter_paths_by_permission(
            user.id,
            [path for path, _ in path_pairs],
            PathAction.READ,
        )
        allowed_set = set(allowed_paths)
        data["items"] = [item for path, item in path_pairs if path in allowed_set]
    return success(data)
