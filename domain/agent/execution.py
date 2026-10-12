import codecs
import json
import logging
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from domain.auth import User
from domain.permission.execution import (
    ExecutionError, execution_context, normalize_path, require_path, require_paths,
)
from domain.permission.types import PathAction
from domain.virtual_fs import VirtualFSService

from .tools import get_tool
from .tools.base import normalize_tool_result, tool_error

logger = logging.getLogger(__name__)


def validate_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = get_tool(name)
    if spec is None:
        raise ExecutionError("unsupported_capability")
    args = {key: value for key, value in arguments.items() if value is not None}
    properties = spec.parameters.get("properties", {})
    if set(args) - set(properties) or any(key not in args for key in spec.parameters.get("required", [])):
        raise ExecutionError("invalid_arguments")
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
    for key, value in args.items():
        expected = types.get(properties[key].get("type"))
        if expected and (not isinstance(value, expected) or (isinstance(value, bool) and expected != bool)):
            raise ExecutionError("invalid_arguments")
        if key in {"path", "src", "dst", "save_to"}:
            args[key] = normalize_path(value)
    for key, low, high in (("page", 1, None), ("page_size", 1, 100), ("top_k", 1, 100),
                           ("max_chars", 1, 100000), ("max_depth", 0, None)):
        if key in args and (args[key] < low or (high is not None and args[key] > high)):
            raise ExecutionError("invalid_arguments")
    for key, values in (("sort_by", {"name", "size", "mtime"}), ("sort_order", {"asc", "desc"}),
                        ("mode", {"filename", "vector"})):
        if key in args and args[key] not in values:
            raise ExecutionError("invalid_arguments")
    if "encoding" in args:
        try:
            codecs.lookup(args["encoding"])
        except LookupError:
            raise ExecutionError("invalid_arguments") from None
    if "q" in args and not args["q"].strip():
        raise ExecutionError("invalid_arguments")
    if name == "web_fetch":
        url = urlsplit(args["url"])
        method = args.get("method", "GET").upper()
        if url.scheme not in {"http", "https"} or not url.hostname or method not in {
            "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
        }:
            raise ExecutionError("invalid_arguments")
        args["method"] = method
        for key in ("headers", "params"):
            if key in args and any(not isinstance(value, str) for value in args[key].values()):
                raise ExecutionError("invalid_arguments")
    if "suffix" in args and (not args["suffix"].strip() or any(c in args["suffix"] for c in ("/", "\\", "\x00"))):
        raise ExecutionError("invalid_arguments")
    return args


async def snapshot_tree(root: str, *, optional: bool = False) -> dict[str, bool]:
    """Enumerate unfiltered paths, failing closed if pagination cannot prove completeness."""
    try:
        info = await VirtualFSService.stat(root)
    except FileNotFoundError:
        if optional:
            return {}
        raise
    except HTTPException as exc:
        if optional and exc.status_code == 404:
            return {}
        raise
    if not isinstance(info, dict):
        raise ExecutionError("permission_scope_unverifiable")
    result = {root: bool(info.get("is_dir"))}
    stack = [root] if result[root] else []
    while stack:
        directory = stack.pop()
        page, cursor, seen_cursors = 1, None, set()
        while True:
            try:
                listing = await VirtualFSService.list_virtual_dir(directory, page, 100, "name", "asc", cursor)
            except Exception as exc:
                raise ExecutionError("permission_scope_unverifiable") from exc
            if not isinstance(listing, dict) or not isinstance(listing.get("items"), list):
                raise ExecutionError("permission_scope_unverifiable")
            items = listing["items"]
            for item in items:
                name = item.get("name")
                if not isinstance(name, str) or not name or "/" in name or "\\" in name:
                    raise ExecutionError("permission_scope_unverifiable")
                path = normalize_path(directory.rstrip("/") + "/" + name)
                if path in result or len(result) >= 10000:
                    raise ExecutionError("permission_scope_unverifiable")
                result[path] = bool(item.get("is_dir"))
                if result[path]:
                    stack.append(path)
            if listing.get("pagination_mode") == "cursor":
                if not listing.get("has_next"):
                    break
                cursor = listing.get("next_cursor")
                if not cursor or cursor in seen_cursors:
                    raise ExecutionError("permission_scope_unverifiable")
                seen_cursors.add(cursor)
            else:
                total = listing.get("total")
                if not isinstance(total, int) or (not items and page * 100 < total):
                    raise ExecutionError("permission_scope_unverifiable")
                if len(items) < min(100, max(0, total - (page - 1) * 100)):
                    raise ExecutionError("permission_scope_unverifiable")
                if page * 100 >= total:
                    break
                page += 1
    return result


async def prepare_scope(name: str, args: dict[str, Any], user: User) -> dict[str, Any]:
    from domain.processors import ProcessorService
    scope: dict[str, Any] = {"user_id": user.id, "permissions": [], "trees": {}}
    permissions: set[tuple[str, str]] = set()

    async def output_path(path: str):
        permissions.add((path, PathAction.WRITE))
        parent = str(PurePosixPath(path).parent)
        while parent != "/":
            try:
                await VirtualFSService.stat(parent)
                break
            except FileNotFoundError:
                permissions.add((parent, PathAction.WRITE))
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                permissions.add((parent, PathAction.WRITE))
            parent = str(PurePosixPath(parent).parent)

    async def tree(root: str, actions: list[str], optional: bool = False):
        await require_paths([(root, action) for action in actions])
        snapshot = await snapshot_tree(root, optional=optional)
        if snapshot:
            scope["trees"][root] = snapshot
        for path in snapshot or {root: False}:
            permissions.update((path, action) for action in actions)
        return snapshot

    if name in {"vfs_move", "vfs_rename", "vfs_copy"}:
        src, dst = args["src"], args["dst"]
        if src == "/" or dst == "/" or src == dst or dst.startswith(src + "/") or src.startswith(dst + "/"):
            raise ExecutionError("invalid_arguments")
        actions = [PathAction.READ] + ([] if name == "vfs_copy" else [PathAction.DELETE])
        await require_paths([(src, action) for action in actions] + [(dst, PathAction.WRITE)])
        source = await tree(src, actions)
        for path in source:
            permissions.add((dst + path[len(src):], PathAction.WRITE))
        # Native overwrite can remove the entire destination subtree.
        if args.get("overwrite"):
            await tree(dst, [PathAction.WRITE, PathAction.DELETE], optional=True)
        await output_path(dst)
    elif name == "vfs_delete":
        if args["path"] == "/":
            raise ExecutionError("invalid_arguments")
        await tree(args["path"], [PathAction.DELETE, PathAction.READ])
    elif name == "processors_run":
        root = args["path"]
        await require_path(root, PathAction.READ)
        processor = ProcessorService.get_processor(args["processor_type"])
        if processor is None:
            raise ExecutionError("unsupported_capability")
        config = args.get("config", {})
        for field in getattr(processor, "config_schema", []):
            value = config.get(field["key"], field.get("default"))
            if field.get("required") and (value is None or value == ""):
                raise ExecutionError("invalid_arguments")
            if value is not None:
                kind = field.get("type")
                if kind == "number" and (isinstance(value, bool) or not isinstance(value, (float, int))):
                    raise ExecutionError("invalid_arguments")
                if kind == "string" and not isinstance(value, str):
                    raise ExecutionError("invalid_arguments")
                if kind == "select" and value not in [option["value"] for option in field.get("options", [])]:
                    raise ExecutionError("invalid_arguments")
        source = await tree(root, [PathAction.READ])
        is_dir = source[root]
        produces = bool(getattr(processor, "produces_file", False))
        if is_dir and getattr(processor, "supports_directory", False) and produces and not user.is_admin:
            raise ExecutionError("permission_scope_unverifiable")
        directory_mode = is_dir and ("max_depth" in args or "suffix" in args)
        overwrite = args.get("overwrite", directory_mode)
        if is_dir and args.get("save_to"):
            raise ExecutionError("invalid_arguments")
        if produces:
            if is_dir:
                if not overwrite and not args.get("suffix"):
                    raise ExecutionError("invalid_arguments")
                for path, child_is_dir in source.items():
                    if not child_is_dir:
                        target = path
                        if not overwrite:
                            p = PurePosixPath(path)
                            target = str(p.with_name(p.stem + args["suffix"] + p.suffix))
                        permissions.add((target, PathAction.WRITE))
            else:
                target = root if overwrite else args.get("save_to")
                if not target:
                    raise ExecutionError("permission_scope_unverifiable")
                await output_path(target)
    else:
        action = PathAction.WRITE if name in {"vfs_write_text", "vfs_mkdir"} else PathAction.READ
        if "path" in args:
            if action == PathAction.WRITE and args["path"] == "/":
                raise ExecutionError("invalid_arguments")
            permissions.add((args["path"], action))
            if action == PathAction.WRITE:
                await require_path(args["path"], action)
                await output_path(args["path"])
    await require_paths(sorted(permissions))
    scope["permissions"] = [list(item) for item in sorted(permissions)]
    return scope


def exception_result(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ExecutionError):
        return tool_error(exc.code)
    if isinstance(exc, (ValueError, TypeError, LookupError, OverflowError)):
        return tool_error("invalid_arguments")
    if isinstance(exc, (FileNotFoundError,)) or isinstance(exc, HTTPException) and exc.status_code == 404:
        return tool_error("path_not_found")
    if isinstance(exc, HTTPException):
        code = {403: "permission_denied", 400: "invalid_arguments", 409: "path_conflict", 501: "unsupported_capability"}.get(exc.status_code, "execution_failed")
        return tool_error(code)
    if isinstance(exc, httpx.TimeoutException):
        return tool_error("request_timeout")
    return tool_error("execution_failed")


_EXPECTED_ERRORS = (
    ExecutionError,
    ValueError, TypeError, LookupError, OverflowError,
    FileNotFoundError, HTTPException,
    httpx.TimeoutException,
)

# Subclasses of the above that are nonetheless real defects. UnicodeEncodeError
# is a ValueError, and an unencodable value reaching a boundary is exactly the
# class of bug these logs exist to surface.
_DEFECT_ERRORS = (UnicodeError,)


def is_expected_error(exc: Exception) -> bool:
    """Whether exc is a normal outcome rather than a defect.

    Mirrors the branches of :func:`exception_result`: everything it maps to a
    specific error code is part of normal control flow and is already reported
    to the model through the tool result. Only the fall-through
    ``execution_failed`` case warrants a traceback.
    """
    return isinstance(exc, _EXPECTED_ERRORS) and not isinstance(exc, _DEFECT_ERRORS)


async def execute_tool(name: str, arguments: dict[str, Any], user: User | None, current_path: str | None = None) -> dict[str, Any]:
    try:
        if user is None or user.disabled:
            raise ExecutionError("permission_denied")
        args = validate_arguments(name, arguments)
        with execution_context({"user_id": user.id, "current_path": current_path}):
            scope = await prepare_scope(name, args, user)
        with execution_context(scope):
            result = await get_tool(name).handler(args)
        # Pydantic search results must remain structured JSON rather than repr strings.
        return normalize_tool_result(json.loads(json.dumps(result, ensure_ascii=False, default=lambda value: value.model_dump(mode="json"))))
    except Exception as exc:
        # The result only carries an error code, so the traceback is the only
        # way to tell a provider crash apart from a rejected argument.
        if not is_expected_error(exc):
            logger.exception("Agent tool execution failed (tool=%s, error=%s)", name, type(exc).__name__)
        return exception_result(exc)
