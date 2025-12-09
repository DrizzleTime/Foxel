from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiofiles
from fastapi import HTTPException

from .file_ops import VirtualFSFileOpsMixin


class VirtualFSTransferMixin(VirtualFSFileOpsMixin):
    @classmethod
    async def move_path(
        cls, src: str, dst: str, overwrite: bool = False, return_debug: bool = True, allow_cross: bool = False
    ):
        adapter_s, adapter_model_s, root_s, rel_s = await cls.resolve_adapter_and_rel(src)
        adapter_d, adapter_model_d, root_d, rel_d = await cls.resolve_adapter_and_rel(dst)
        debug_info = {
            "src": src,
            "dst": dst,
            "rel_s": rel_s,
            "rel_d": rel_d,
            "root_s": root_s,
            "root_d": root_d,
            "overwrite": overwrite,
            "operation": "move",
            "queued": False,
        }
        if not rel_s:
            raise HTTPException(400, detail="Cannot move or rename mount root")
        if not rel_d:
            raise HTTPException(400, detail="Invalid destination")

        if adapter_model_s.id != adapter_model_d.id:
            if not allow_cross:
                raise HTTPException(400, detail="Cross-adapter move not supported")
            queue_info = await cls._enqueue_cross_mount_transfer(
                operation="move",
                src=src,
                dst=dst,
                overwrite=overwrite,
            )
            debug_info.update(queue_info)
            return debug_info if return_debug else None

        exists_func = getattr(adapter_s, "exists", None)
        stat_func = getattr(adapter_s, "stat_path", None)
        delete_func = await cls._ensure_method(adapter_s, "delete")
        move_func = await cls._ensure_method(adapter_s, "move")

        dst_exists = False
        dst_stat = None
        if callable(exists_func):
            dst_exists = await exists_func(root_d, rel_d)
        if callable(stat_func):
            dst_stat = await stat_func(root_d, rel_d)
        debug_info["dst_exists"] = dst_exists
        debug_info["dst_stat"] = dst_stat

        if dst_exists and not overwrite:
            kind = None
            fs_path = None
            if dst_stat:
                kind = "dir" if dst_stat.get("is_dir") else "file"
                fs_path = dst_stat.get("path")
            raise HTTPException(
                409,
                detail=f"Destination already exists(kind={kind}, fs_path={fs_path}, rel_d={rel_d}, overwrite={overwrite})",
            )
        if dst_exists and overwrite:
            try:
                await delete_func(root_s, rel_d)
                debug_info["pre_delete"] = "ok"
            except Exception as exc:
                debug_info["pre_delete"] = f"error:{exc}"
                raise HTTPException(500, detail=f"Pre-delete failed before overwrite: {exc}")

        if rel_s == rel_d:
            debug_info["noop"] = True
            return debug_info if return_debug else None

        try:
            await move_func(root_s, rel_s, rel_d)
            debug_info["moved"] = True
        except FileNotFoundError:
            raise HTTPException(404, detail="Source not found")
        except FileExistsError:
            raise HTTPException(409, detail="Destination already exists (race condition after pre-check)")
        except IsADirectoryError:
            raise HTTPException(400, detail="Invalid directory operation")
        except Exception as exc:
            raise HTTPException(500, detail=f"Move failed: {exc}")

        return debug_info if return_debug else None

    @classmethod
    async def rename_path(cls, src: str, dst: str, overwrite: bool = False, return_debug: bool = True):
        adapter_s, adapter_model_s, root_s, rel_s = await cls.resolve_adapter_and_rel(src)
        adapter_d, adapter_model_d, root_d, rel_d = await cls.resolve_adapter_and_rel(dst)
        debug_info = {
            "src": src,
            "dst": dst,
            "rel_s": rel_s,
            "rel_d": rel_d,
            "root_s": root_s,
            "root_d": root_d,
            "overwrite": overwrite,
        }
        if adapter_model_s.id != adapter_model_d.id:
            raise HTTPException(400, detail="Cross-adapter rename not supported")
        if not rel_s:
            raise HTTPException(400, detail="Cannot rename mount root")
        if not rel_d:
            raise HTTPException(400, detail="Invalid destination")

        exists_func = getattr(adapter_s, "exists", None)
        stat_func = getattr(adapter_s, "stat_path", None)
        delete_func = await cls._ensure_method(adapter_s, "delete")
        rename_func = await cls._ensure_method(adapter_s, "rename")

        dst_exists = False
        dst_stat = None
        if callable(exists_func):
            dst_exists = await exists_func(root_d, rel_d)
        if callable(stat_func):
            dst_stat = await stat_func(root_d, rel_d)
        debug_info["dst_exists"] = dst_exists
        debug_info["dst_stat"] = dst_stat

        if dst_exists and not overwrite:
            kind = None
            fs_path = None
            if dst_stat:
                kind = "dir" if dst_stat.get("is_dir") else "file"
                fs_path = dst_stat.get("path")
            raise HTTPException(
                409,
                detail=f"Destination already exists(kind={kind}, fs_path={fs_path}, rel_d={rel_d}, overwrite={overwrite})",
            )
        if dst_exists and overwrite:
            try:
                await delete_func(root_s, rel_d)
                debug_info["pre_delete"] = "ok"
            except Exception as exc:
                debug_info["pre_delete"] = f"error:{exc}"
                raise HTTPException(500, detail=f"Pre-delete failed before overwrite: {exc}")

        if rel_s == rel_d:
            debug_info["noop"] = True
            return debug_info if return_debug else None

        try:
            await rename_func(root_s, rel_s, rel_d)
            debug_info["renamed"] = True
        except FileNotFoundError:
            raise HTTPException(404, detail="Source not found")
        except FileExistsError:
            raise HTTPException(409, detail="Destination already exists (race condition after pre-check)")
        except IsADirectoryError:
            raise HTTPException(400, detail="Invalid directory operation")
        except Exception as exc:
            raise HTTPException(500, detail=f"Rename failed: {exc}")

        return debug_info if return_debug else None

    @classmethod
    async def copy_path(
        cls, src: str, dst: str, overwrite: bool = False, return_debug: bool = True, allow_cross: bool = False
    ):
        adapter_s, adapter_model_s, root_s, rel_s = await cls.resolve_adapter_and_rel(src)
        adapter_d, adapter_model_d, root_d, rel_d = await cls.resolve_adapter_and_rel(dst)
        debug_info = {
            "src": src,
            "dst": dst,
            "rel_s": rel_s,
            "rel_d": rel_d,
            "root_s": root_s,
            "root_d": root_d,
            "overwrite": overwrite,
            "operation": "copy",
            "queued": False,
        }
        if not rel_s:
            raise HTTPException(400, detail="Cannot copy mount root")
        if not rel_d:
            raise HTTPException(400, detail="Invalid destination")

        if adapter_model_s.id != adapter_model_d.id:
            if not allow_cross:
                raise HTTPException(400, detail="Cross-adapter copy not supported")
            queue_info = await cls._enqueue_cross_mount_transfer(
                operation="copy",
                src=src,
                dst=dst,
                overwrite=overwrite,
            )
            debug_info.update(queue_info)
            return debug_info if return_debug else None

        exists_func = getattr(adapter_s, "exists", None)
        stat_func = getattr(adapter_s, "stat_path", None)
        delete_func = getattr(adapter_s, "delete", None)
        copy_func = await cls._ensure_method(adapter_s, "copy")

        dst_exists = False
        dst_stat = None
        if callable(exists_func):
            dst_exists = await exists_func(root_d, rel_d)
        if callable(stat_func):
            dst_stat = await stat_func(root_d, rel_d)
        debug_info["dst_exists"] = dst_exists
        debug_info["dst_stat"] = dst_stat

        if dst_exists and not overwrite:
            raise HTTPException(409, detail="Destination already exists")
        if dst_exists and overwrite and callable(delete_func):
            try:
                await delete_func(root_s, rel_d)
                debug_info["pre_delete"] = "ok"
            except Exception as exc:
                debug_info["pre_delete"] = f"error:{exc}"
                raise HTTPException(500, detail=f"Pre-delete failed: {exc}")

        if rel_s == rel_d:
            debug_info["noop"] = True
            return debug_info if return_debug else None

        try:
            await copy_func(root_s, rel_s, rel_d, overwrite=overwrite)
            debug_info["copied"] = True
        except FileNotFoundError:
            raise HTTPException(404, detail="Source not found")
        except FileExistsError:
            raise HTTPException(409, detail="Destination already exists (race condition)")
        except Exception as exc:
            raise HTTPException(500, detail=f"Copy failed: {exc}")

        return debug_info if return_debug else None

    @classmethod
    async def _enqueue_cross_mount_transfer(cls, operation: str, src: str, dst: str, overwrite: bool) -> Dict[str, Any]:
        if operation not in {"move", "copy"}:
            raise HTTPException(400, detail="Unsupported transfer operation")

        adapter_s, adapter_model_s, _, _ = await cls.resolve_adapter_and_rel(src)
        adapter_d, adapter_model_d, root_d, rel_d = await cls.resolve_adapter_and_rel(dst)
        if adapter_model_s.id == adapter_model_d.id:
            raise HTTPException(400, detail="Cross-adapter transfer requested but adapters are identical")

        dst_exists = False
        exists_func = getattr(adapter_d, "exists", None)
        if callable(exists_func):
            dst_exists = await exists_func(root_d, rel_d)
        else:
            try:
                await cls.stat_file(dst)
                dst_exists = True
            except FileNotFoundError:
                dst_exists = False
            except HTTPException as exc:
                if exc.status_code == 404:
                    dst_exists = False
                else:
                    raise

        if dst_exists and not overwrite:
            raise HTTPException(409, detail="Destination already exists")

        payload = {
            "operation": operation,
            "src": src,
            "dst": dst,
            "overwrite": overwrite,
        }

        from domain.tasks.task_queue import task_queue_service

        task = await task_queue_service.add_task("cross_mount_transfer", payload)
        return {
            "queued": True,
            "task_id": task.id,
            "task_name": "cross_mount_transfer",
            "dst_exists": dst_exists,
            "cross_adapter": True,
        }

    @classmethod
    async def run_cross_mount_transfer_task(cls, task: "Task") -> Dict[str, Any]:
        from domain.tasks.task_queue import task_queue_service

        params = task.task_info or {}
        operation = params.get("operation")
        src = params.get("src")
        dst = params.get("dst")
        overwrite = bool(params.get("overwrite", False))

        if operation not in {"move", "copy"}:
            raise ValueError(f"Unsupported cross mount operation: {operation}")
        if not src or not dst:
            raise ValueError("Missing src or dst for cross mount transfer")

        adapter_s, adapter_model_s, root_s, rel_s = await cls.resolve_adapter_and_rel(src)
        adapter_d, adapter_model_d, root_d, rel_d = await cls.resolve_adapter_and_rel(dst)

        await task_queue_service.update_meta(task.id, {"operation": operation, "src": src, "dst": dst})

        if adapter_model_s.id == adapter_model_d.id:
            if operation == "move":
                await cls.move_path(src, dst, overwrite=overwrite, return_debug=False, allow_cross=False)
            else:
                await cls.copy_path(src, dst, overwrite=overwrite, return_debug=False, allow_cross=False)
            return {
                "mode": "direct",
                "operation": operation,
                "src": src,
                "dst": dst,
                "files": 0,
                "bytes": 0,
            }

        if not rel_s:
            raise ValueError("Cannot transfer mount root")
        if not rel_d:
            raise ValueError("Invalid destination")

        dst_exists = False
        exists_func = getattr(adapter_d, "exists", None)
        if callable(exists_func):
            dst_exists = await exists_func(root_d, rel_d)
        else:
            try:
                await cls.stat_file(dst)
                dst_exists = True
            except FileNotFoundError:
                dst_exists = False
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise

        if dst_exists and not overwrite:
            raise ValueError("Destination already exists")
        if dst_exists and overwrite:
            await cls.delete_path(dst)

        try:
            src_stat = await cls.stat_file(src)
        except HTTPException as exc:
            if exc.status_code == 404:
                raise FileNotFoundError(src) from exc
            raise

        src_is_dir = bool(src_stat.get("is_dir"))

        files_to_transfer: List[Dict[str, Any]] = []
        dirs_to_create: List[str] = []

        await task_queue_service.update_progress(
            task.id,
            {
                "stage": "preparing",
                "percent": 0.0,
                "detail": "Collecting source entries",
            },
        )

        if src_is_dir:
            if rel_d:
                dirs_to_create.append(rel_d)
            list_dir = await cls._ensure_method(adapter_s, "list_dir")
            stack: List[Tuple[str, str, str]] = [(rel_s, rel_d, "")]
            page_size = 200

            while stack:
                current_rel, current_dst_rel, current_relative = stack.pop()
                page = 1
                while True:
                    entries, total = await list_dir(root_s, current_rel, page, page_size, "name", "asc")
                    if not entries and (total or 0) == 0:
                        break
                    for entry in entries:
                        name = entry.get("name")
                        if not name:
                            continue
                        child_rel = cls._join_rel(current_rel, name)
                        child_dst_rel = cls._join_rel(current_dst_rel, name)
                        child_relative = cls._join_rel(current_relative, name)
                        if entry.get("is_dir"):
                            dirs_to_create.append(child_dst_rel)
                            stack.append((child_rel, child_dst_rel, child_relative))
                        else:
                            files_to_transfer.append(
                                {
                                    "src_rel": child_rel,
                                    "dst_rel": child_dst_rel,
                                    "relative_rel": child_relative or name,
                                    "size": entry.get("size"),
                                    "name": name,
                                }
                            )
                    if total is None or page * page_size >= (total or 0):
                        break
                    page += 1
        else:
            relative_rel = rel_s or (src_stat.get("name") or "file")
            files_to_transfer.append(
                {
                    "src_rel": rel_s,
                    "dst_rel": rel_d,
                    "relative_rel": relative_rel,
                    "size": src_stat.get("size"),
                    "name": src_stat.get("name") or rel_s.split("/")[-1],
                }
            )
            parent_dir = cls._parent_rel(rel_d)
            if parent_dir:
                dirs_to_create.append(parent_dir)

        cls.CROSS_TRANSFER_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        temp_dir = cls.CROSS_TRANSFER_TEMP_ROOT / task.id
        temp_dir.mkdir(parents=True, exist_ok=True)

        bytes_downloaded = 0
        total_dynamic_bytes = sum((f["size"] or 0) for f in files_to_transfer)

        try:
            for job in files_to_transfer:
                src_abs = cls._build_absolute_path(adapter_model_s.path, job["src_rel"])
                data = await cls.read_file(src_abs)
                temp_path = temp_dir / job["relative_rel"]
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(temp_path, "wb") as f:
                    await f.write(data)
                actual_size = len(data)
                job["temp_path"] = temp_path
                prev_size = job.get("size") or 0
                if prev_size <= 0:
                    total_dynamic_bytes += actual_size
                    job_size = actual_size
                else:
                    job_size = prev_size
                job["size"] = job_size
                bytes_downloaded += actual_size
                percent = None
                total_for_percent = total_dynamic_bytes if total_dynamic_bytes else bytes_downloaded
                if total_for_percent:
                    percent = min(100.0, round(bytes_downloaded / total_for_percent * 100, 2))
                await task_queue_service.update_progress(
                    task.id,
                    {
                        "stage": "downloading",
                        "percent": percent,
                        "bytes_done": bytes_downloaded,
                        "bytes_total": total_dynamic_bytes or None,
                        "detail": f"Downloaded {job['name']}",
                    },
                )

            mkdir_func = await cls._ensure_method(adapter_d, "mkdir")
            ensured_dirs: set[str] = set()

            async def ensure_dir(rel_path: str):
                if not rel_path or rel_path in ensured_dirs:
                    return
                parent = cls._parent_rel(rel_path)
                if parent:
                    await ensure_dir(parent)
                try:
                    await mkdir_func(root_d, rel_path)
                except FileExistsError:
                    pass
                except HTTPException as exc:
                    if exc.status_code not in {409, 400}:
                        raise
                except Exception:
                    pass
                ensured_dirs.add(rel_path)

            for dir_rel in sorted({d for d in dirs_to_create if d}, key=lambda x: x.count("/")):
                await ensure_dir(dir_rel)

            uploaded_bytes = 0
            total_bytes = sum((f["size"] or 0) for f in files_to_transfer)

            async def iter_temp_file(path: Path, chunk_size: int = 512 * 1024):
                async with aiofiles.open(path, "rb") as f:
                    while True:
                        chunk = await f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk

            for job in files_to_transfer:
                parent_dir = cls._parent_rel(job["dst_rel"])
                if parent_dir:
                    await ensure_dir(parent_dir)
                dst_abs = cls._build_absolute_path(adapter_model_d.path, job["dst_rel"])
                temp_path: Path = job["temp_path"]
                await cls.write_file_stream(dst_abs, iter_temp_file(temp_path), overwrite=overwrite)
                uploaded_bytes += job["size"] or 0
                percent = None
                if total_bytes:
                    percent = min(100.0, round(uploaded_bytes / total_bytes * 100, 2))
                await task_queue_service.update_progress(
                    task.id,
                    {
                        "stage": "uploading",
                        "percent": percent,
                        "bytes_done": uploaded_bytes,
                        "bytes_total": total_bytes or None,
                        "detail": f"Uploaded {job['name']}",
                    },
                )

            if operation == "move":
                await cls.delete_path(src)

            await task_queue_service.update_progress(
                task.id,
                {
                    "stage": "completed",
                    "percent": 100.0,
                    "bytes_done": total_bytes,
                    "bytes_total": total_bytes,
                    "detail": "Completed",
                },
            )

            await task_queue_service.update_meta(
                task.id,
                {
                    "files": len(files_to_transfer),
                    "directories": len({d for d in dirs_to_create if d}),
                    "bytes": total_bytes,
                    "operation": operation,
                },
            )

            return {
                "mode": "cross",
                "operation": operation,
                "src": src,
                "dst": dst,
                "files": len(files_to_transfer),
                "bytes": total_bytes,
            }

        finally:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception:
                pass
