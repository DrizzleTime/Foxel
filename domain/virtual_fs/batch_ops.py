import posixpath

from fastapi import HTTPException

from domain.permission.execution import guard_path
from domain.permission.service import PermissionService
from domain.permission.types import PathAction

from .routes import VirtualFSRouteMixin
from .types import BatchDeleteRequest, BatchTransferRequest


def _err_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        return detail if isinstance(detail, str) else str(detail)
    return str(exc) or exc.__class__.__name__


class VirtualFSBatchOpsMixin(VirtualFSRouteMixin):
    """Batch operations built on the single-item primitives.

    Every item is executed independently: one failure does not abort the
    rest. The response always carries per-item results so the client can
    report partial success and retry failed items.
    """

    @classmethod
    async def batch_delete(cls, paths: list[str], *, user_id: int) -> dict:
        paths = BatchDeleteRequest(paths=paths).paths
        results: list[dict] = []
        for path in paths:
            try:
                await PermissionService.require_path_permission(user_id, path, PathAction.DELETE)
                await guard_path(path, PathAction.DELETE)
                await cls.delete(path)
                results.append({"src": path, "ok": True})
            except Exception as exc:
                results.append({"src": path, "ok": False, "error": _err_text(exc)})
        failed = sum(1 for item in results if not item["ok"])
        return {"results": results, "succeeded": len(results) - failed, "failed": failed}

    @classmethod
    async def _batch_transfer(cls, srcs: list[str], dst: str, overwrite: bool, copy: bool, user_id: int) -> dict:
        body = BatchTransferRequest(srcs=srcs, dst=dst)
        srcs, dst = body.srcs, body.dst
        results: list[dict] = []
        for src in srcs:
            target = posixpath.join(dst, posixpath.basename(src))
            try:
                action = PathAction.READ if copy else PathAction.DELETE
                await PermissionService.require_path_permission(user_id, src, action)
                await guard_path(src, action)
                await PermissionService.require_path_permission(user_id, target, PathAction.WRITE)
                await guard_path(target, PathAction.WRITE)
                if target == src or target.startswith(src.rstrip("/") + "/"):
                    raise HTTPException(400, "Destination must be outside the source")
                if copy:
                    result = await cls.copy(src, target, overwrite)
                else:
                    result = await cls.move(src, target, overwrite)
                item = {"src": src, "dst": target, "ok": True, "queued": bool(result.get("queued"))}
                if result.get("task_id"):
                    item["task_id"] = result["task_id"]
                results.append(item)
            except Exception as exc:
                results.append({"src": src, "dst": target, "ok": False, "error": _err_text(exc)})
        failed = sum(1 for item in results if not item["ok"])
        return {"results": results, "succeeded": len(results) - failed, "failed": failed}

    @classmethod
    async def batch_move(cls, srcs: list[str], dst: str, overwrite: bool = False, *, user_id: int) -> dict:
        return await cls._batch_transfer(srcs, dst, overwrite, copy=False, user_id=user_id)

    @classmethod
    async def batch_copy(cls, srcs: list[str], dst: str, overwrite: bool = False, *, user_id: int) -> dict:
        return await cls._batch_transfer(srcs, dst, overwrite, copy=True, user_id=user_id)
