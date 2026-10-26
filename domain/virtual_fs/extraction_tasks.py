import asyncio
from contextlib import aclosing, suppress
import mimetypes
from pathlib import Path
import posixpath
import shutil
import tempfile
from types import SimpleNamespace

import aiofiles
from fastapi import HTTPException

from domain.adapters.archive import MAX_EXTRACTED_BYTES
from domain.permission.execution import guard_path
from domain.permission.service import PermissionService
from domain.permission.types import PathAction
from models.database import UserAccount


class ExtractionTaskMixin:
    EXTRACTION_TEMP_ROOT = Path("data/tmp/extraction")

    @classmethod
    async def _extraction_user(cls, user_id):
        if not await UserAccount.filter(id=user_id, disabled=False).exists():
            raise HTTPException(403, "Extraction task user is no longer active")
        PermissionService.clear_cache(user_id)

    @classmethod
    async def run_extraction_task(cls, task):
        from domain.adapters.providers.local import LocalAdapter
        from domain.tasks import task_queue_service

        params = task.task_info
        user_id = params["user_id"]
        await cls._extraction_user(user_id)
        context = await cls._prepare_extraction(params["src"], params["dst"], user_id)
        if cls._extraction_bindings(context) != params["bindings"]:
            raise HTTPException(409, "Storage mounts changed after extraction was queued")

        async def progress(stage, percent, done=None, total=None, detail=None):
            await task_queue_service.update_progress(task.id, {
                "stage": stage, "percent": percent, "bytes_done": done,
                "bytes_total": total, "detail": detail,
            })

        await task_queue_service.update_meta(task.id, {"src": params["src"], "dst": params["dst"]})
        await progress("preparing", 0)
        await asyncio.to_thread(cls.EXTRACTION_TEMP_ROOT.mkdir, parents=True, exist_ok=True)
        workspace = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix=task.id + "-", dir=cls.EXTRACTION_TEMP_ROOT))
        try:
            archive = workspace / "archive.zip"
            source = context["source"]
            downloaded = 0
            total = source["size"] or 0
            if total > MAX_EXTRACTED_BYTES:
                raise HTTPException(400, "Archive download exceeds the 10 GiB limit")
            await progress("downloading", 0, 0, total or None)
            async with aiofiles.open(archive, "wb") as output:
                async with aclosing(cls._compression_source_chunks(source)) as chunks:
                    async for chunk in chunks:
                        downloaded += len(chunk)
                        if downloaded > MAX_EXTRACTED_BYTES:
                            raise HTTPException(400, "Archive download exceeds the 10 GiB limit")
                        await output.write(chunk)
                        await progress("downloading", min(39.0, downloaded / total * 40) if total else 0,
                                       downloaded, total or None)
            if total and downloaded != total:
                raise HTTPException(409, "Archive source changed during download")

            await progress("extracting", 40, downloaded, downloaded)
            local = LocalAdapter(SimpleNamespace(config={"root": str(workspace)}))
            extraction = asyncio.create_task(local.extract(str(workspace), "archive.zip", "contents"))
            try:
                # The extraction thread must finish before its workspace is removed.
                result = await asyncio.shield(extraction)
            except asyncio.CancelledError:
                with suppress(Exception):
                    await extraction
                raise
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            entries = result["entries"]
            files = [entry for entry in entries if not entry["is_dir"]]
            total_bytes = sum(entry["size"] for entry in files)
            await task_queue_service.update_meta(task.id, {"files": len(files), "bytes": total_bytes})

            # Revalidate user, mounts and conflicts after downloading and extracting.
            await cls._extraction_user(user_id)
            context = await cls._prepare_extraction(params["src"], params["dst"], user_id)
            if cls._extraction_bindings(context) != params["bindings"]:
                raise HTTPException(409, "Storage mounts changed during extraction")
            for entry in entries:
                await cls._check_extraction_output(context, entry["name"], user_id)

            await progress("uploading", 60, 0, total_bytes)
            # Paths this task creates, in creation order. Each one is recorded right after
            # the "does not exist yet" check and before it is written, so a file left half
            # written by the failing step is also ours to remove.
            created = []
            try:
                uploaded = await cls._upload_extracted(params, context, entries, workspace,
                                                       total_bytes, user_id, created, progress)
            except Exception:
                if params.get("cleanup_on_failure") and created:
                    report = await cls._cleanup_extraction(context, created, user_id)
                    await task_queue_service.update_meta(task.id, {"cleanup": report})
                raise
            await progress("completed", 100, uploaded, total_bytes)
            return {"path": context["dst"], "files": len(files), "bytes": uploaded, "mode": "server"}
        finally:
            await asyncio.to_thread(shutil.rmtree, workspace)

    @classmethod
    async def _upload_extracted(cls, params, context, entries, workspace, total_bytes, user_id,
                                created, progress):
        from domain.tasks import TaskService
        from .file_ops import VirtualFSFileOpsMixin

        path, adapter, root, rel = await cls._check_extraction_output(context, "", user_id)
        await cls._require_extraction_absent(adapter, root, rel)
        created.append({"path": path, "is_dir": True})
        await adapter.mkdir(root, rel)
        uploaded = 0
        for index, entry in enumerate(entries):
            await cls._extraction_user(user_id)
            await PermissionService.require_path_permission(user_id, params["src"], PathAction.READ)
            await guard_path(params["src"], PathAction.READ)
            path, adapter, root, rel = await cls._check_extraction_output(context, entry["name"], user_id)
            parent = await cls._compression_stat(adapter, root, posixpath.dirname(rel))
            if not parent.get("is_dir") or parent.get("is_symlink"):
                raise HTTPException(409, "Extraction destination parent changed")
            await cls._require_extraction_absent(adapter, root, rel)
            created.append({"path": path, "is_dir": bool(entry["is_dir"])})
            if entry["is_dir"]:
                await adapter.mkdir(root, rel)
                continue
            staged = workspace / "contents" / entry["name"]
            upload = getattr(adapter, "write_upload_file", None)
            if callable(upload):
                with staged.open("rb") as incoming:
                    written = await upload(root, rel, incoming, posixpath.basename(rel), entry["size"],
                                           mimetypes.guess_type(rel)[0] or "application/octet-stream")
            else:
                async def file_chunks():
                    async with aiofiles.open(staged, "rb") as incoming:
                        while chunk := await incoming.read(cls.COMPRESSION_CHUNK_SIZE):
                            yield chunk

                stream = getattr(adapter, "write_file_stream", None)
                if callable(stream):
                    async with aclosing(file_chunks()) as chunks:
                        written = await stream(root, rel, chunks)
                else:
                    written = await adapter.write_file(root, rel, await asyncio.to_thread(staged.read_bytes))
            final_path, _ = VirtualFSFileOpsMixin._normalize_written_result(path, context["model"], written, entry["size"])
            if final_path != path:   # the adapter stored the file under another name
                created.append({"path": final_path, "is_dir": False})
            await TaskService.trigger_tasks("file_written", final_path)
            uploaded += entry["size"]
            percent = 60 + (uploaded / total_bytes if total_bytes else (index + 1) / max(1, len(entries))) * 39
            await progress("uploading", percent, uploaded, total_bytes, final_path)
        return uploaded

    @classmethod
    async def _cleanup_extraction(cls, context, created, user_id):
        """Remove paths this extraction task created; keep and report anything else.

        Files go first (newest first), then directories deepest first. A directory is only
        removed when it is empty, because adapters may delete directories recursively and
        it could hold files this task did not create. Every removal re-checks DELETE
        permission, path guards and the storage mount, so permission or mount changes after
        the task was queued leave the path in place.
        """
        removed, kept = 0, []
        seen, ordered = set(), []
        for item in reversed(created):
            if item["path"] not in seen:
                seen.add(item["path"])
                ordered.append(item)
        files = [item for item in ordered if not item["is_dir"]]
        dirs = sorted((item for item in ordered if item["is_dir"]),
                      key=lambda item: item["path"].count("/"), reverse=True)
        try:
            await cls._extraction_user(user_id)
        except HTTPException as exc:
            kept = [{"path": item["path"], "reason": str(exc.detail)} for item in files + dirs]
            return cls._cleanup_report(0, kept)
        for item in files + dirs:
            path = item["path"]
            try:
                reason = await cls._remove_extracted_path(context, path, item["is_dir"], user_id)
            except HTTPException as exc:
                reason = str(exc.detail)
            except Exception as exc:
                # Adapter errors can embed URLs or credentials; report the error type only.
                reason = f"Delete failed ({type(exc).__name__})"
            if reason is None:
                removed += 1
            elif reason:
                kept.append({"path": path, "reason": reason})
        return cls._cleanup_report(removed, kept)

    # Archives may hold up to 100k entries and task meta is polled by the UI, so the report
    # counts removed paths and lists at most this many kept ones.
    CLEANUP_REPORT_LIMIT = 100

    @classmethod
    def _cleanup_report(cls, removed, kept):
        return {"removed": removed, "kept": kept[:cls.CLEANUP_REPORT_LIMIT], "kept_total": len(kept)}

    @classmethod
    async def _remove_extracted_path(cls, context, path, is_dir, user_id):
        """Delete one created path. Returns None when removed, "" when it is already gone,
        or the reason it was kept."""
        adapter, model, root, rel = await cls.resolve_adapter_and_rel(path)
        if [model.id, root] != [context["model"].id, context["root"]]:
            return "Storage mounts changed during extraction"
        try:
            stat = await adapter.stat_file(root, rel)
        except FileNotFoundError:
            return ""   # never written (the failing step) or already gone: nothing to report
        await PermissionService.require_path_permission(user_id, path, PathAction.DELETE)
        await guard_path(path, PathAction.DELETE)
        if not isinstance(stat, dict) or stat.get("is_symlink") or bool(stat.get("is_dir")) != is_dir:
            return "Path type changed after it was created"
        if is_dir and not await cls._extraction_dir_empty(adapter, root, rel):
            return "Directory contains files not created by this task"
        delete = getattr(adapter, "delete", None)
        if not callable(delete):
            return "Storage adapter does not support deleting files"
        await delete(root, rel)
        # Some adapters report success without removing the path (e.g. a directory marker
        # addressed without its trailing slash), so only report what is actually gone.
        try:
            await adapter.stat_file(root, rel)
        except FileNotFoundError:
            return None
        return "Path still exists after delete"

    @staticmethod
    async def _extraction_dir_empty(adapter, root, rel):
        listing = await adapter.list_dir(root, rel, 1, 1)
        if isinstance(listing, dict):
            items, total = listing.get("items", []), listing.get("total")
            if listing.get("has_next"):
                return False
        else:
            items, total = listing
        return not items and not total
