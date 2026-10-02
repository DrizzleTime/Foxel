"""Request-local authority propagated only to MCP-originated background tasks."""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

from .service import PermissionService
from models.database import UserAccount


class ExecutionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_scope: ContextVar[dict[str, Any] | None] = ContextVar("foxel_execution_scope", default=None)


def normalize_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ExecutionError("invalid_arguments")
    parts = value.strip().replace("\\", "/").split("/")
    if any(part in {".", ".."} for part in parts):
        raise ExecutionError("invalid_arguments")
    return "/" + "/".join(part for part in parts if part)


@contextmanager
def execution_context(scope: dict[str, Any] | None):
    token = _scope.set(scope)
    try:
        yield
    finally:
        _scope.reset(token)


def execution_scope() -> dict[str, Any] | None:
    return deepcopy(_scope.get())


def current_user_id() -> int:
    scope = _scope.get()
    if scope is None:
        raise ExecutionError("permission_denied")
    return scope["user_id"]


async def require_path(path: str, action: str) -> str:
    path = normalize_path(path)
    await require_paths([(path, action)])
    return path


async def require_paths(paths: list[tuple[str, str]]) -> None:
    user_id = current_user_id()
    if not await UserAccount.filter(id=user_id, disabled=False).exists():
        raise ExecutionError("permission_denied")
    PermissionService.clear_cache(user_id)
    for path, action in paths:
        if not await PermissionService.check_path_permission(user_id, normalize_path(path), action):
            raise ExecutionError("permission_denied")


async def guard_path(path: str, action: str) -> None:
    scope = _scope.get()
    if scope is None:
        return
    path = normalize_path(path)
    permissions = scope.get("permissions")
    if permissions is not None and [path, action] not in permissions:
        raise ExecutionError("permission_scope_changed")
    await validate_scope()
    await require_path(path, action)


async def validate_scope() -> None:
    scope = _scope.get()
    if scope is None or "permissions" not in scope:
        return
    await require_paths([tuple(item) for item in scope["permissions"]])
    from domain.agent.execution import snapshot_tree
    for root, expected in scope.get("trees", {}).items():
        actual = await snapshot_tree(root)
        if actual != expected:
            raise ExecutionError("permission_scope_changed")


def forget_tree(root: str) -> None:
    scope = _scope.get()
    if scope is not None:
        scope.get("trees", {}).pop(normalize_path(root), None)
