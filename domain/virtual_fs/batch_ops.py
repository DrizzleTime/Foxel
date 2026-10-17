from fastapi import HTTPException

from .routes import VirtualFSRouteMixin

MAX_BATCH_ITEMS = 200


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
    async def batch_delete(cls, paths: list[str]) -> dict:
        paths = list(dict.fromkeys(paths))[:MAX_BATCH_ITEMS]
        results: list[dict] = []
        for path in paths:
            try:
                await cls.delete(path)
                results.append({"src": path, "ok": True})
            except Exception as exc:
                results.append({"src": path, "ok": False, "error": _err_text(exc)})
        failed = sum(1 for item in results if not item["ok"])
        return {"results": results, "succeeded": len(results) - failed, "failed": failed}

    @classmethod
    async def _batch_transfer(cls, srcs: list[str], dst: str, overwrite: bool, copy: bool) -> dict:
        srcs = list(dict.fromkeys(srcs))[:MAX_BATCH_ITEMS]
        dst = dst.rstrip("/") or "/"
        results: list[dict] = []
        for src in srcs:
            name = src.rstrip("/").split("/")[-1]
            target = dst if dst == "/" else f"{dst}/{name}"
            try:
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
    async def batch_move(cls, srcs: list[str], dst: str, overwrite: bool = False) -> dict:
        return await cls._batch_transfer(srcs, dst, overwrite, copy=False)

    @classmethod
    async def batch_copy(cls, srcs: list[str], dst: str, overwrite: bool = False) -> dict:
        return await cls._batch_transfer(srcs, dst, overwrite, copy=True)
