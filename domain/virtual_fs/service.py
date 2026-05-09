from .common import VirtualFSCommonMixin
from .resolver import VirtualFSResolverMixin
from .listing import VirtualFSListingMixin
from .file_ops import VirtualFSFileOpsMixin
from .transfer import VirtualFSTransferMixin
from .processing import VirtualFSProcessingMixin
from .temp_link import VirtualFSTempLinkMixin
from .routes import VirtualFSRouteMixin


class VirtualFSService(
    VirtualFSRouteMixin,
    VirtualFSTempLinkMixin,
    VirtualFSProcessingMixin,
    VirtualFSTransferMixin,
    VirtualFSFileOpsMixin,
    VirtualFSListingMixin,
    VirtualFSResolverMixin,
    VirtualFSCommonMixin,
):
    @classmethod
    async def list_directory(
        cls,
        path: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
        cursor: str | None = None,
    ):
        """列出目录内容"""
        return await cls.list_virtual_dir(path, page_num, page_size, sort_by, sort_order, cursor)

    @classmethod
    async def list_directory_with_permission(
        cls,
        path: str,
        user_id: int,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
        cursor: str | None = None,
    ):
        """列出目录内容（带权限过滤）"""
        full_path = cls._normalize_path(path).rstrip("/") or "/"
        result = await cls.list_virtual_dir_with_permission(
            full_path, user_id, page_num, page_size, sort_by, sort_order, cursor
        )
        pagination = {
            "mode": result.get("pagination_mode", "paged") if isinstance(result, dict) else "paged",
            "page_size": result.get("page_size", page_size) if isinstance(result, dict) else page_size,
        }
        if pagination["mode"] == "cursor":
            pagination.update(
                {
                    "cursor": result.get("cursor") if isinstance(result, dict) else cursor,
                    "next_cursor": result.get("next_cursor") if isinstance(result, dict) else None,
                    "has_next": bool(result.get("has_next")) if isinstance(result, dict) else False,
                }
            )
        else:
            pagination.update(
                {
                    "total": result.get("total", 0) if isinstance(result, dict) else 0,
                    "page": result.get("page", page_num) if isinstance(result, dict) else page_num,
                    "pages": result.get("pages", 0) if isinstance(result, dict) else 0,
                }
            )
        return {
            "path": full_path,
            "entries": result.get("items", []) if isinstance(result, dict) else [],
            "pagination": pagination,
        }
