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


def listing_pagination(
    result: Any,
    *,
    page_num: int = 1,
    page_size: int = 50,
    cursor: str | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """把 list_virtual_dir / page / cursor_page 结果规范成对外 pagination。"""
    data = result if isinstance(result, dict) else {}
    items = data.get("items") or []
    mode = data.get("pagination_mode") or "paged"
    pagination: dict[str, Any] = {
        "mode": mode,
        "page_size": data.get("page_size", page_size),
    }
    if mode == "cursor":
        pagination.update(
            {
                "cursor": data.get("cursor", cursor),
                "next_cursor": data.get("next_cursor"),
                "has_next": bool(data.get("has_next")),
            }
        )
    else:
        total = data.get("total")
        pages = data.get("pages")
        pagination.update(
            {
                "total": 0 if total is None else total,
                "page": data.get("page", page_num),
                "pages": 0 if pages is None else pages,
            }
        )
    return items, pagination


def dir_listing(
    result: Any,
    *,
    path: str,
    page_num: int = 1,
    page_size: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """对外目录列表载荷：path / entries / pagination。"""
    items, pagination = listing_pagination(
        result, page_num=page_num, page_size=page_size, cursor=cursor
    )
    return {"path": path, "entries": items, "pagination": pagination}


def error(msg: str, code: int = 1, data: Optional[Any] = None):
    return {"code": code, "msg": msg, "data": data}
