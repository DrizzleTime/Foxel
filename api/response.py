from typing import Any, Optional


def success(data: Any = None, msg: str = "ok", code: int = 0):
    """标准成功响应包装。"""
    return {"code": code, "msg": msg, "data": data}


def page(items: list[Any], total: int, page: int, page_size: int):
    """统一分页数据结构。"""
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


def error(msg: str, code: int = 1, data: Optional[Any] = None):
    return {"code": code, "msg": msg, "data": data}
