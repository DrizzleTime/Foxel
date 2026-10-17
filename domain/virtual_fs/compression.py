import posixpath

from fastapi import HTTPException

from domain.permission.execution import ExecutionError, guard_path, normalize_path
from domain.permission.service import PermissionService
from domain.permission.types import PathAction
from domain.tasks import TaskService
from models import StorageAdapter

from .resolver import VirtualFSResolverMixin
from .compression_tasks import CompressionTaskMixin


class VirtualFSCompressionMixin(CompressionTaskMixin, VirtualFSResolverMixin):
    @staticmethod
    def _can_upload_archive(adapter):
        return getattr(adapter, "supports_upload", True) and any(
            callable(getattr(adapter, method, None))
            for method in ("write_upload_file", "write_file_stream", "write_file")
        )

    @staticmethod
    def _can_download_archive_source(adapter):
        return any(callable(getattr(adapter, method, None)) for method in ("stream_file", "read_file"))

    @classmethod
    async def compression_capabilities(cls, path: str):
        try:
            path = normalize_path(path)
        except ExecutionError as exc:
            raise HTTPException(400, "Invalid path") from exc
        try:
            adapter, _, root, rel = await cls.resolve_adapter_and_rel(path)
        except HTTPException as exc:
            if exc.status_code == 404:
                return {"formats": [], "native": False}
            raise
        method = getattr(adapter, "get_compression_capabilities", None)
        native = False
        if callable(method) and callable(getattr(adapter, "compress", None)):
            capabilities = await method(root, rel)
            native = "zip" in capabilities.get("formats", [])
        supported = native or (cls._can_download_archive_source(adapter) and cls._can_upload_archive(adapter))
        return {"formats": ["zip"] if supported else [], "native": native}

    @classmethod
    async def compress(cls, sources: list[str], dst: str, user_id: int):
        context = await cls._prepare_compression(sources, dst, user_id)
        adapter, root, dst_rel = context["adapter"], context["root"], context["dst_rel"]
        jobs, dst = context["sources"], context["dst"]
        capabilities = await cls.compression_capabilities(posixpath.dirname(dst))
        native = capabilities["native"] and all(
            job["model"].id == context["model"].id and job["root"] == root for job in jobs
        )
        if not native:
            if not cls._can_upload_archive(adapter) or any(
                not cls._can_download_archive_source(job["adapter"]) for job in jobs
            ):
                raise HTTPException(501, "Storage adapter does not support archive download or upload")
            from domain.tasks import task_queue_service

            task = await task_queue_service.add_task("compress_archive", {
                "sources": [job["path"] for job in jobs], "dst": dst, "user_id": user_id,
                "bindings": cls._compression_bindings(context),
            })
            await task_queue_service.update_progress(task.id, {"stage": "preparing", "percent": 0.0})
            return {"path": dst, "compressed": False, "queued": True,
                    "task_id": task.id, "task_name": task.name}

        for job in jobs:
            await cls._check_compression_source(adapter, root, job["rel"], job["path"], user_id)
        try:
            result = await adapter.compress(root, [job["rel"] for job in jobs], dst_rel)
        except FileExistsError as exc:
            raise HTTPException(409, "Archive destination already exists") from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "Archive source or destination parent not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        queued = bool(result.get("queued"))
        if not queued:
            await TaskService.trigger_tasks("file_written", dst)
        return {"path": dst, "compressed": not queued, "queued": queued,
                "upstream_task_id": result.get("upstream_task_id")}

    @staticmethod
    def _compression_bindings(context):
        return [[context["model"].id, context["root"]]] + [
            [job["model"].id, job["root"]] for job in context["sources"]
        ]

    @staticmethod
    async def _compression_stat(adapter, root, rel):
        # A mount root is a directory even for flat providers such as Telegram
        # and S3, whose stat_file only accepts files or nonempty prefixes.
        if not rel:
            return {"is_dir": True}
        try:
            return await adapter.stat_file(root, rel)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Archive source or destination parent not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @classmethod
    async def _prepare_compression(cls, sources, dst, user_id):
        from .types import CompressRequest

        body = CompressRequest(sources=sources, dst=dst)
        sources, dst = body.sources, body.dst
        await PermissionService.require_path_permission(user_id, dst, PathAction.WRITE)
        await guard_path(dst, PathAction.WRITE)
        adapter, model, root, dst_rel = await cls.resolve_adapter_and_rel(dst)
        if not dst_rel or not dst.lower().endswith(".zip"):
            raise HTTPException(400, "Archive destination must be a .zip file")
        mounts = await StorageAdapter.filter(enabled=True)
        jobs = []
        names = set()
        for source in sources:
            await PermissionService.require_path_permission(user_id, source, PathAction.READ)
            await guard_path(source, PathAction.READ)
            source_adapter, source_model, source_root, rel = await cls.resolve_adapter_and_rel(source)
            if not rel:
                raise HTTPException(400, "Cannot compress a storage mount root")
            if dst == source or dst.startswith(source + "/"):
                raise HTTPException(400, "Archive destination must be outside its sources")
            if any(mount.path.startswith(source + "/") for mount in mounts):
                raise HTTPException(400, "Cannot compress a directory containing nested storage mounts")
            if any(source.startswith(other + "/") for other in sources):
                continue
            name = posixpath.basename(source)
            if name in names:
                raise HTTPException(400, "Archive sources must have distinct names")
            names.add(name)
            stat = await cls._compression_stat(source_adapter, source_root, rel)
            if stat.get("is_symlink"):
                raise HTTPException(400, "Cannot compress symbolic links")
            jobs.append({"adapter": source_adapter, "model": source_model, "root": source_root,
                         "rel": rel, "path": source})

        parent = await cls._compression_stat(adapter, root, posixpath.dirname(dst_rel))
        if not parent.get("is_dir"):
            raise HTTPException(400, "Archive destination parent must be a directory")
        if parent.get("is_symlink"):
            raise HTTPException(400, "Cannot create archives through symbolic links")
        try:
            await adapter.stat_file(root, dst_rel)
        except FileNotFoundError:
            pass
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        else:
            raise HTTPException(409, "Archive destination already exists")
        return {"adapter": adapter, "model": model, "root": root, "dst_rel": dst_rel,
                "dst": dst, "sources": jobs}

    @classmethod
    async def _check_compression_source(cls, adapter, root, rel, path, user_id, entries=None, archive_name=None):
        """Check every descendant: native operations bypass VFS listing filters."""
        await PermissionService.require_path_permission(user_id, path, PathAction.READ)
        await guard_path(path, PathAction.READ)
        try:
            item = await adapter.stat_file(root, rel)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Archive source not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if item.get("is_symlink"):
            raise HTTPException(400, "Cannot compress symbolic links")
        if entries is not None:
            archive_name = archive_name or posixpath.basename(path)
            entries.append({"adapter": adapter, "root": root, "rel": rel, "path": path,
                            "archive_name": archive_name, "is_dir": bool(item.get("is_dir")),
                            "size": item.get("size")})
        if not item.get("is_dir"):
            return
        page, cursor, seen_cursors = 1, None, set()
        while True:
            kwargs = {"cursor": cursor} if cursor else {}
            listing = await adapter.list_dir(root, rel, page, 100, **kwargs)
            if isinstance(listing, dict):
                items, total = listing.get("items", []), listing.get("total")
            else:
                items, total = listing
            for child in items:
                name = child.get("name", "")
                if not isinstance(name, str) or not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
                    raise HTTPException(502, "Storage returned an invalid archive source name")
                child_name = archive_name + "/" + name if archive_name else None
                await cls._check_compression_source(adapter, root, rel + "/" + name, path + "/" + name,
                                                    user_id, entries, child_name)
            if isinstance(listing, dict) and listing.get("pagination_mode") == "cursor":
                if not listing.get("has_next"):
                    break
                cursor = listing.get("next_cursor")
                if not cursor or cursor in seen_cursors:
                    raise HTTPException(502, "Storage returned invalid pagination")
                seen_cursors.add(cursor)
            else:
                if not isinstance(total, int) or total < 0 or len(items) < min(100, max(0, total - (page - 1) * 100)):
                    raise HTTPException(502, "Storage returned incomplete archive source listing")
                if page * 100 >= total:
                    break
                page += 1
