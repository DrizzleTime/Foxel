from fastapi import APIRouter, Depends, Query

from domain.auth.service import get_current_active_user
from domain.auth.types import User
from domain.virtual_fs.search_service import VirtualFSSearchService

router = APIRouter(prefix="/api/fs/search", tags=["search"])


@router.get("")
async def search_files(
    q: str = Query(..., description="搜索查询"),
    top_k: int = Query(10, description="返回结果数量"),
    mode: str = Query("vector", description="搜索模式: 'vector' 或 'filename'"),
    page: int = Query(1, description="分页页码，仅在文件名搜索模式下生效"),
    page_size: int = Query(10, description="分页大小，仅在文件名搜索模式下生效"),
    user: User = Depends(get_current_active_user),
):
    if not q.strip():
        return {"items": [], "query": q}

    top_k = max(top_k, 1)
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)

    return await VirtualFSSearchService.search(q, top_k, mode, page, page_size)
