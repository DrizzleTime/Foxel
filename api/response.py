from typing import Any, Optional


def success(data: Any = None, msg: str = "ok", code: int = 0):
    """标准成功响应包装。"""
    return {"code": code, "msg": msg, "data": data}


def page(items: list[Any], total: int, page: int, page_size: int):
    """统一分页数据结构。"""
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages, "pagination_mode": "paged"}


def cursor_page(
    items: list[Any],
    page_size: int,
    *,
    cursor: str | None = None,
    next_cursor: str | None = None,
):
    """无总数游标分页结构。"""
    return {
        "items": items,
        "page_size": page_size,
        "pagination_mode": "cursor",
        "cursor": cursor,
        "next_cursor": next_cursor,
        "has_next": bool(next_cursor),
    }


def error(msg: str, code: int = 1, data: Optional[Any] = None):
    return {"code": code, "msg": msg, "data": data}
