import inspect
from functools import wraps
from typing import Any, Iterable, Mapping

from fastapi import HTTPException

from .service import PermissionService


def _get_user_id(user: Any) -> int | None:
    if user is None:
        return None
    if isinstance(user, Mapping):
        raw = user.get("id") or user.get("user_id")
        return int(raw) if isinstance(raw, int) else None
    value = getattr(user, "id", None) or getattr(user, "user_id", None)
    return int(value) if isinstance(value, int) else None


def _resolve_expr(bound_args: Mapping[str, Any], expr: str) -> Any:
    parts = [p for p in (expr or "").split(".") if p]
    if not parts:
        return None
    cur: Any = bound_args.get(parts[0])
    for part in parts[1:]:
        if cur is None:
            return None
        if isinstance(cur, Mapping):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def require_system_permission(permission_code: str, *, user_kw: str = "current_user"):
    """
    在 endpoint 内部执行系统/适配器权限校验。

    设计目标：
    - 保持和当前“在函数体内手写 require_*”一致的行为：失败会被外层 @audit 捕获记录
    - 不依赖 FastAPI dependencies（避免权限失败发生在 endpoint 之外）
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            bound = inspect.signature(func).bind_partial(*args, **kwargs)
            bound.apply_defaults()
            user_id = _get_user_id(bound.arguments.get(user_kw))
            if user_id is None:
                raise HTTPException(status_code=401, detail="Unauthorized")
            await PermissionService.require_system_permission(user_id, permission_code)

            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

        return wrapper

    return decorator


def require_path_permission(action: str, path_expr: str, *, user_kw: str = "current_user"):
    """
    在 endpoint 内部执行路径权限校验。

    path_expr 支持：
    - "full_path"
    - "body.src" / "body.dst"
    - "payload.paths"（list[str] 会逐个检查）
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            bound = inspect.signature(func).bind_partial(*args, **kwargs)
            bound.apply_defaults()
            user_id = _get_user_id(bound.arguments.get(user_kw))
            if user_id is None:
                raise HTTPException(status_code=401, detail="Unauthorized")

            value = _resolve_expr(bound.arguments, path_expr)
            paths: Iterable[Any]
            if isinstance(value, (list, tuple, set)):
                paths = value
            else:
                paths = [value]

            for path in paths:
                if path is None:
                    raise HTTPException(status_code=400, detail="Missing path")
                await PermissionService.require_path_permission(user_id, str(path), action)

            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

        return wrapper

    return decorator

