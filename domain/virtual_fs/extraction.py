import posixpath

from fastapi import HTTPException

from domain.permission.execution import ExecutionError, guard_path, normalize_path
from domain.permission.service import PermissionService
from domain.permission.types import PathAction
from models import StorageAdapter

from .extraction_tasks import ExtractionTaskMixin


class VirtualFSExtractionMixin(ExtractionTaskMixin):
    @classmethod
    def _can_extract_to(cls, adapter):
        return (getattr(adapter, "supports_directories", True)
                and callable(getattr(adapter, "mkdir", None))
                and cls._can_upload_archive(adapter))

    @classmethod
    async def extraction_capabilities(cls, path):
        try:
            path = normalize_path(path)
        except ExecutionError as exc:
            raise HTTPException(400, "Invalid path") from exc
        try:
            adapter, _, _, _ = await cls.resolve_adapter_and_rel(path)
        except HTTPException as exc:
            if exc.status_code == 404:
                return {"formats": [], "native": False}
            raise
        supported = cls._can_download_archive_source(adapter) and cls._can_extract_to(adapter)
        # All VFS extraction uses the queue so each output path can be authorized.
        return {"formats": ["zip"] if supported else [], "native": False}

    @classmethod
    async def extract(cls, src, dst, user_id, cleanup_on_failure=False):
        from domain.tasks import task_queue_service

        context = await cls._prepare_extraction(src, dst, user_id)
        if cleanup_on_failure:
            # Cleanup removes paths under the destination, so require DELETE up front
            # instead of discovering a missing permission only after a failure.
            await PermissionService.require_path_permission(user_id, context["dst"], PathAction.DELETE)
            await guard_path(context["dst"], PathAction.DELETE)
            if not callable(getattr(context["adapter"], "delete", None)):
                raise HTTPException(501, "Storage adapter does not support deleting extracted files")
        task = await task_queue_service.add_task("extract_archive", {
            "src": context["src"], "dst": context["dst"], "user_id": user_id,
            "bindings": cls._extraction_bindings(context),
            "cleanup_on_failure": bool(cleanup_on_failure),
        })
        await task_queue_service.update_progress(task.id, {"stage": "preparing", "percent": 0.0})
        return {"path": context["dst"], "extracted": False, "queued": True,
                "task_id": task.id, "task_name": task.name}

    @staticmethod
    def _extraction_bindings(context):
        return [[context["model"].id, context["root"]],
                [context["source"]["model"].id, context["source"]["root"]]]

    @classmethod
    async def _prepare_extraction(cls, src, dst, user_id):
        from .types import ExtractRequest

        body = ExtractRequest(src=src, dst=dst)
        src, dst = body.src, body.dst
        await PermissionService.require_path_permission(user_id, src, PathAction.READ)
        await guard_path(src, PathAction.READ)
        await PermissionService.require_path_permission(user_id, dst, PathAction.WRITE)
        await guard_path(dst, PathAction.WRITE)
        source_adapter, source_model, source_root, src_rel = await cls.resolve_adapter_and_rel(src)
        adapter, model, root, dst_rel = await cls.resolve_adapter_and_rel(dst)
        if not src_rel or not src.lower().endswith(".zip"):
            raise HTTPException(400, "Archive source must be a .zip file")
        if not dst_rel or dst == src or dst.startswith(src + "/"):
            raise HTTPException(400, "Extraction destination must be a new directory")
        if not cls._can_download_archive_source(source_adapter) or not cls._can_extract_to(adapter):
            raise HTTPException(501, "Storage adapter does not support archive download, upload or directories")
        mounts = await StorageAdapter.filter(enabled=True)
        if any(mount.path.startswith(dst + "/") for mount in mounts):
            raise HTTPException(400, "Cannot extract into a directory containing nested storage mounts")
        source_stat = await cls._compression_stat(source_adapter, source_root, src_rel)
        if source_stat.get("is_dir") or source_stat.get("is_symlink"):
            raise HTTPException(400, "Archive source must be a regular file without symbolic links")
        parent = await cls._compression_stat(adapter, root, posixpath.dirname(dst_rel))
        if not parent.get("is_dir") or parent.get("is_symlink"):
            raise HTTPException(400, "Extraction destination parent must be a directory without symbolic links")
        await cls._require_extraction_absent(adapter, root, dst_rel)
        return {"adapter": adapter, "model": model, "root": root, "dst_rel": dst_rel, "dst": dst,
                "src": src, "source": {"adapter": source_adapter, "model": source_model,
                                         "root": source_root, "rel": src_rel, "path": src,
                                         "size": source_stat.get("size")}}

    @staticmethod
    async def _require_extraction_absent(adapter, root, rel):
        try:
            await adapter.stat_file(root, rel)
        except FileNotFoundError:
            return
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        raise HTTPException(409, "Extraction destination already exists")

    @classmethod
    async def _check_extraction_output(cls, context, name, user_id):
        path = context["dst"] + ("/" + name if name else "")
        await PermissionService.require_path_permission(user_id, path, PathAction.WRITE)
        await guard_path(path, PathAction.WRITE)
        adapter, model, root, rel = await cls.resolve_adapter_and_rel(path)
        if [model.id, root] != [context["model"].id, context["root"]]:
            raise HTTPException(409, "Storage mounts changed during extraction")
        return path, adapter, root, rel
