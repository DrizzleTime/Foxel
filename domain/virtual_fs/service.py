from __future__ import annotations

import base64
import hashlib
import hmac
import mimetypes
import re
import shutil
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Tuple, TYPE_CHECKING, Union

import aiofiles
from fastapi import HTTPException, UploadFile
from fastapi.responses import Response

from api.response import page
from domain.adapters.registry import runtime_registry
from domain.config.service import ConfigService
from models import StorageAdapter
from domain.tasks.service import TaskService
from domain.virtual_fs.thumbnail import (
    get_or_create_thumb,
    is_image_filename,
    is_raw_filename,
    is_video_filename,
)
from domain.ai.service import VectorDBService

if TYPE_CHECKING:
    from domain.tasks.task_queue import Task


class VirtualFSService:
    CROSS_TRANSFER_TEMP_ROOT = Path("data/tmp/cross_transfer")
    DIRECT_REDIRECT_CONFIG_KEY = "enable_direct_download_307"

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _build_absolute_path(mount_path: str, rel_path: str) -> str:
        rel_norm = rel_path.lstrip("/")
        mount_norm = mount_path.rstrip("/")
        if not mount_norm:
            return "/" + rel_norm if rel_norm else "/"
        return f"{mount_norm}/{rel_norm}" if rel_norm else mount_norm

    @staticmethod
    def _join_rel(base: str, name: str) -> str:
        if not base:
            return name.lstrip("/")
        if not name:
            return base
        return f"{base.rstrip('/')}/{name.lstrip('/')}"

    @staticmethod
    def _parent_rel(rel: str) -> str:
        if not rel or "/" not in rel:
            return ""
        return rel.rsplit("/", 1)[0]

    @staticmethod
    async def _ensure_method(adapter: Any, method: str):
        func = getattr(adapter, method, None)
        if not callable(func):
            raise HTTPException(501, detail=f"Adapter does not implement {method}")
        return func

    @classmethod
    async def resolve_adapter_by_path(cls, path: str) -> Tuple[StorageAdapter, str]:
        norm = cls._normalize_path(path)
        adapters = await StorageAdapter.filter(enabled=True)
        best = None
        for adapter in adapters:
            if norm == adapter.path or norm.startswith(adapter.path.rstrip("/") + "/"):
                if best is None or len(adapter.path) > len(best.path):
                    best = adapter
        if not best:
            raise HTTPException(404, detail="No storage adapter for path")
        rel = norm[len(best.path) :].lstrip("/")
        return best, rel

    @classmethod
    async def resolve_adapter_and_rel(cls, path: str):
        norm = cls._normalize_path(path)
        adapter_model, rel = await cls.resolve_adapter_by_path(norm)
        adapter_instance = runtime_registry.get(adapter_model.id)
        if not adapter_instance:
            await runtime_registry.refresh()
            adapter_instance = runtime_registry.get(adapter_model.id)
            if not adapter_instance:
                raise HTTPException(
                    404, detail=f"Adapter instance for ID {adapter_model.id} not found or failed to load."
                )
        effective_root = adapter_instance.get_effective_root(adapter_model.sub_path)
        return adapter_instance, adapter_model, effective_root, rel

    @classmethod
    async def maybe_redirect_download(cls, adapter_instance, adapter_model, root: str, rel: str):
        if not rel or rel.endswith("/"):
            return None

        config = getattr(adapter_model, "config", {}) or {}
        if not config.get(cls.DIRECT_REDIRECT_CONFIG_KEY):
            return None

        handler = getattr(adapter_instance, "get_direct_download_response", None)
        if not callable(handler):
            return None

        try:
            response = await handler(root, rel)
        except FileNotFoundError:
            raise
        except Exception:
            return None

        if isinstance(response, Response):
            return response
        return None

    @classmethod
    async def path_is_directory(cls, path: str) -> bool:
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        rel = rel.rstrip("/")
        if rel == "":
            return True
        stat_func = getattr(adapter_instance, "stat_file", None)
        if not callable(stat_func):
            raise HTTPException(501, detail="Adapter does not implement stat_file")
        try:
            info = await stat_func(root, rel)
        except FileNotFoundError:
            raise HTTPException(404, detail="Path not found")
        if isinstance(info, dict):
            return bool(info.get("is_dir"))
        return False

    @classmethod
    async def list_virtual_dir(
        cls,
        path: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Dict:
        norm = cls._normalize_path(path).rstrip("/") or "/"
        adapters = await StorageAdapter.filter(enabled=True)

        child_mount_entries: List[str] = []
        norm_prefix = norm.rstrip("/")
        for adapter in adapters:
            if adapter.path == norm:
                continue
            if adapter.path.startswith(norm_prefix + "/"):
                tail = adapter.path[len(norm_prefix) :].lstrip("/")
                if "/" not in tail:
                    child_mount_entries.append(tail)
        child_mount_entries = sorted(set(child_mount_entries))

        sort_field = sort_by.lower()
        reverse = sort_order.lower() == "desc"

        def build_sort_key(item: Dict) -> Tuple:
            key = (not bool(item.get("is_dir")),)
            if sort_field == "name":
                key += (str(item.get("name", "")).lower(),)
            elif sort_field == "size":
                key += (int(item.get("size", 0)),)
            elif sort_field == "mtime":
                key += (int(item.get("mtime", 0)),)
            else:
                key += (str(item.get("name", "")).lower(),)
            return key

        def annotate_entry(entry: Dict) -> None:
            if not entry.get("is_dir"):
                name = entry.get("name", "")
                entry["has_thumbnail"] = bool(is_image_filename(name) or is_video_filename(name))
            else:
                entry["has_thumbnail"] = False

        try:
            adapter_model, rel = await cls.resolve_adapter_by_path(norm)
            adapter_instance = runtime_registry.get(adapter_model.id)
            if not adapter_instance:
                await runtime_registry.refresh()
                adapter_instance = runtime_registry.get(adapter_model.id)

            if adapter_instance:
                effective_root = adapter_instance.get_effective_root(adapter_model.sub_path)
            else:
                adapter_model = None
                effective_root = ""
                rel = ""
        except HTTPException:
            adapter_model = None
            adapter_instance = None
            effective_root = ""
            rel = ""

        adapter_entries_page: List[Dict] = []
        adapter_entries_for_merge: List[Dict] = []
        adapter_total = 0
        covered = set()

        if adapter_model and adapter_instance:
            list_dir = await cls._ensure_method(adapter_instance, "list_dir")
            try:
                adapter_entries_page, adapter_total = await list_dir(
                    effective_root, rel, page_num, page_size, sort_by, sort_order
                )
            except NotADirectoryError:
                raise HTTPException(400, detail="Not a directory")

            adapter_entries_for_merge = adapter_entries_page

            if child_mount_entries and adapter_total > len(adapter_entries_page):
                full_page_size = adapter_total
                if full_page_size > 0:
                    adapter_entries_for_merge, adapter_total = await list_dir(
                        effective_root, rel, 1, full_page_size, sort_by, sort_order
                    )
                else:
                    adapter_entries_for_merge = adapter_entries_page

            for item in adapter_entries_for_merge:
                covered.add(item["name"])

        mount_entries = []
        for name in child_mount_entries:
            if name not in covered:
                mount_entries.append(
                    {"name": name, "is_dir": True, "size": 0, "mtime": 0, "type": "mount", "has_thumbnail": False}
                )

        if mount_entries:
            for ent in adapter_entries_for_merge:
                annotate_entry(ent)
            combined_entries = adapter_entries_for_merge + [{**ent, "has_thumbnail": False} for ent in mount_entries]
            combined_entries.sort(key=build_sort_key, reverse=reverse)

            total_entries = len(combined_entries)
            start_idx = (page_num - 1) * page_size
            end_idx = start_idx + page_size
            page_entries = combined_entries[start_idx:end_idx]
            return page(page_entries, total_entries, page_num, page_size)

        annotate_entry_list = adapter_entries_page or []
        for ent in annotate_entry_list:
            annotate_entry(ent)
        return page(adapter_entries_page, adapter_total, page_num, page_size)

    @classmethod
    async def read_file(cls, path: str) -> Union[bytes, Any]:
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        if rel.endswith("/") or rel == "":
            raise HTTPException(400, detail="Path is a directory")
        read_func = await cls._ensure_method(adapter_instance, "read_file")
        return await read_func(root, rel)

    @classmethod
    async def write_file(cls, path: str, data: bytes):
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        if rel.endswith("/"):
            raise HTTPException(400, detail="Invalid file path")
        write_func = await cls._ensure_method(adapter_instance, "write_file")
        await write_func(root, rel, data)
        await TaskService.trigger_tasks("file_written", path)

    @classmethod
    async def write_file_stream(cls, path: str, data_iter: AsyncIterator[bytes], overwrite: bool = True):
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        if rel.endswith("/"):
            raise HTTPException(400, detail="Invalid file path")
        exists_func = getattr(adapter_instance, "exists", None)
        if not overwrite and callable(exists_func):
            try:
                if await exists_func(root, rel):
                    raise HTTPException(409, detail="Destination exists")
            except HTTPException:
                raise
            except Exception:
                pass

        size = 0
        stream_func = getattr(adapter_instance, "write_file_stream", None)
        if callable(stream_func):
            size = await stream_func(root, rel, data_iter)
        else:
            buf = bytearray()
            async for chunk in data_iter:
                if chunk:
                    buf.extend(chunk)
            write_func = await cls._ensure_method(adapter_instance, "write_file")
            await write_func(root, rel, bytes(buf))
            size = len(buf)

        await TaskService.trigger_tasks("file_written", path)
        return size

    @classmethod
    async def make_dir(cls, path: str):
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        if not rel:
            return
        mkdir_func = await cls._ensure_method(adapter_instance, "mkdir")
        await mkdir_func(root, rel)

    @classmethod
    async def delete_path(cls, path: str):
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        if not rel:
            raise HTTPException(400, detail="Cannot delete root")
        delete_func = await cls._ensure_method(adapter_instance, "delete")
        await delete_func(root, rel)
        await TaskService.trigger_tasks("file_deleted", path)

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
        debug_info = {"src": src, "dst": dst, "rel_s": rel_s, "rel_d": rel_d, "root_s": root_s, "root_d": root_d, "overwrite": overwrite}
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
    async def stream_file(cls, path: str, range_header: str | None):
        adapter_instance, adapter_model, root, rel = await cls.resolve_adapter_and_rel(path)
        if not rel or rel.endswith("/"):
            raise HTTPException(400, detail="Path is a directory")
        if is_raw_filename(rel):
            import io

            import rawpy
            from PIL import Image

            try:
                raw_data = await cls.read_file(path)
                try:
                    with rawpy.imread(io.BytesIO(raw_data)) as raw:
                        try:
                            thumb = raw.extract_thumb()
                        except rawpy.LibRawNoThumbnailError:
                            thumb = None

                        if thumb is not None and thumb.format in [rawpy.ThumbFormat.JPEG, rawpy.ThumbFormat.BITMAP]:
                            im = Image.open(io.BytesIO(thumb.data))
                        else:
                            rgb = raw.postprocess(use_camera_wb=False, use_auto_wb=True, output_bps=8)
                            im = Image.fromarray(rgb)
                except Exception as exc:
                    print(f"rawpy processing failed: {exc}")
                    raise exc

                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=90)
                content = buf.getvalue()
                return Response(content=content, media_type="image/jpeg")
            except Exception as exc:
                raise HTTPException(500, detail=f"RAW file processing failed: {exc}")

        redirect_response = await cls.maybe_redirect_download(adapter_instance, adapter_model, root, rel)
        if redirect_response is not None:
            return redirect_response

        stream_impl = getattr(adapter_instance, "stream_file", None)
        if callable(stream_impl):
            return await stream_impl(root, rel, range_header)
        data = await cls.read_file(path)
        mime, _ = mimetypes.guess_type(rel)
        return Response(content=data, media_type=mime or "application/octet-stream")

    @classmethod
    async def _gather_vector_index(cls, full_path: str, limit: int = 20):
        vector_db = VectorDBService()
        try:
            raw_results = await vector_db.search_by_path("vector_collection", full_path, max(limit * 2, 20))
        except Exception:
            return None

        matched = []
        if raw_results:
            buckets = raw_results if isinstance(raw_results, list) else [raw_results]
            for bucket in buckets:
                if not bucket:
                    continue
                for record in bucket:
                    entity = dict((record or {}).get("entity") or {})
                    source_path = entity.get("source_path") or entity.get("path") or ""
                    if source_path != full_path:
                        continue
                    entry = {
                        "chunk_id": str(entity.get("chunk_id")) if entity.get("chunk_id") is not None else None,
                        "type": entity.get("type"),
                        "mime": entity.get("mime"),
                        "name": entity.get("name"),
                        "start_offset": entity.get("start_offset"),
                        "end_offset": entity.get("end_offset"),
                        "vector_id": entity.get("vector_id"),
                    }
                    text = entity.get("text") or entity.get("description")
                    if text:
                        preview_limit = 400
                        entry["preview"] = text[:preview_limit]
                        entry["preview_truncated"] = len(text) > preview_limit
                    matched.append(entry)

        if not matched:
            return {"total": 0, "entries": [], "by_type": {}, "has_more": False}

        type_counts: Dict[str, int] = {}
        for item in matched:
            key = item.get("type") or "unknown"
            type_counts[key] = type_counts.get(key, 0) + 1

        has_more = len(matched) > limit
        return {
            "total": len(matched),
            "entries": matched[:limit],
            "by_type": type_counts,
            "has_more": has_more,
            "limit": limit,
        }

    @classmethod
    async def stat_file(cls, path: str):
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        stat_func = getattr(adapter_instance, "stat_file", None)
        if not callable(stat_func):
            raise HTTPException(501, detail="Adapter does not implement stat_file")
        info = await stat_func(root, rel)

        if isinstance(info, dict):
            info.setdefault("path", path)
            try:
                is_dir = bool(info.get("is_dir"))
            except Exception:
                is_dir = False
            rel_name = rel.rstrip("/").split("/")[-1] if rel else path.rstrip("/").split("/")[-1]
            name_hint = str(info.get("name") or rel_name or "")
            info["has_thumbnail"] = bool(not is_dir and (is_image_filename(name_hint) or is_video_filename(name_hint)))
            if not is_dir:
                vector_index = await cls._gather_vector_index(path)
                if vector_index is not None:
                    info["vector_index"] = vector_index

        return info

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

    @classmethod
    async def process_file(
        cls,
        path: str,
        processor_type: str,
        config: dict,
        save_to: str | None = None,
        overwrite: bool = False,
    ) -> Any:
        # Local import to avoid circular dependency on module load.
        from domain.processors.service import get_processor

        processor = get_processor(processor_type)
        if not processor:
            raise HTTPException(400, detail=f"Processor {processor_type} not found")

        actual_is_dir = await cls.path_is_directory(path)

        supported_exts = getattr(processor, "supported_exts", None) or []
        allowed_exts = {str(ext).lower().lstrip(".") for ext in supported_exts if isinstance(ext, str)}

        def matches_extension(rel_path: str) -> bool:
            if not allowed_exts:
                return True
            if "." not in rel_path:
                return "" in allowed_exts
            ext = rel_path.rsplit(".", 1)[-1].lower()
            return ext in allowed_exts or f".{ext}" in allowed_exts

        def coerce_result_bytes(result: Any) -> bytes:
            if isinstance(result, Response):
                return result.body
            if isinstance(result, (bytes, bytearray)):
                return bytes(result)
            if isinstance(result, str):
                return result.encode("utf-8")
            raise HTTPException(500, detail="Processor must return bytes/Response when produces_file=True")

        def build_absolute_path(mount_path: str, rel_path: str) -> str:
            rel_norm = rel_path.lstrip("/")
            mount_norm = mount_path.rstrip("/")
            if not mount_norm:
                return "/" + rel_norm if rel_norm else "/"
            return f"{mount_norm}/{rel_norm}" if rel_norm else mount_norm

        if actual_is_dir:
            if save_to:
                raise HTTPException(400, detail="Directory processing does not support custom save_to path")
            if not overwrite:
                raise HTTPException(400, detail="Directory processing requires overwrite")

            adapter_instance, adapter_model, root, rel = await cls.resolve_adapter_and_rel(path)
            rel = rel.rstrip("/")
            list_dir = await cls._ensure_method(adapter_instance, "list_dir")
            processed_count = 0
            stack: List[str] = [rel]
            page_size = 200

            while stack:
                current = stack.pop()
                page = 1
                while True:
                    entries, total = await list_dir(root, current, page, page_size, "name", "asc")
                    if not entries and (total or 0) == 0:
                        break

                    for entry in entries:
                        name = entry.get("name")
                        if not name:
                            continue
                        child_rel = f"{current}/{name}" if current else name
                        if entry.get("is_dir"):
                            stack.append(child_rel)
                            continue
                        if not matches_extension(child_rel):
                            continue
                        absolute_path = build_absolute_path(adapter_model.path, child_rel)
                        data = await cls.read_file(absolute_path)
                        result = await processor.process(data, absolute_path, config)
                        if getattr(processor, "produces_file", False):
                            result_bytes = coerce_result_bytes(result)
                            await cls.write_file(absolute_path, result_bytes)
                        processed_count += 1

                    if total is None or page * page_size >= total:
                        break
                    page += 1

            return {"processed_files": processed_count}

        data = await cls.read_file(path)
        result = await processor.process(data, path, config)

        target_path = save_to
        if overwrite and not target_path:
            target_path = path

        if target_path and getattr(processor, "produces_file", False):
            result_bytes = coerce_result_bytes(result)
            await cls.write_file(target_path, result_bytes)
            return {"saved_to": target_path}

        return result

    @classmethod
    async def get_temp_link_secret_key(cls) -> bytes:
        return await ConfigService.get_secret_key("TEMP_LINK_SECRET_KEY", None)

    @classmethod
    async def generate_temp_link_token(cls, path: str, expires_in: int = 3600) -> str:
        if expires_in <= 0:
            expiration_time = "0"
        else:
            expiration_time = str(int(time.time() + expires_in))

        message = f"{path}:{expiration_time}".encode("utf-8")
        secret_key = await cls.get_temp_link_secret_key()
        signature = hmac.new(secret_key, message, hashlib.sha256).digest()

        token_data = f"{path}:{expiration_time}:{base64.urlsafe_b64encode(signature).decode('utf-8')}"
        return base64.urlsafe_b64encode(token_data.encode("utf-8")).decode("utf-8")

    @classmethod
    async def verify_temp_link_token(cls, token: str) -> str:
        try:
            decoded_token = base64.urlsafe_b64decode(token).decode("utf-8")
            path, expiration_time_str, signature_b64 = decoded_token.rsplit(":", 2)
            signature = base64.urlsafe_b64decode(signature_b64)
        except (ValueError, TypeError, base64.binascii.Error):
            raise HTTPException(status_code=400, detail="Invalid token format")

        if expiration_time_str != "0":
            expiration_time = int(expiration_time_str)
            if time.time() > expiration_time:
                raise HTTPException(status_code=410, detail="Link has expired")

        message = f"{path}:{expiration_time_str}".encode("utf-8")
        secret_key = await cls.get_temp_link_secret_key()
        expected_signature = hmac.new(secret_key, message, hashlib.sha256).digest()

        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        return path

    # --- Route-friendly helpers ---

    @classmethod
    async def serve_file(cls, full_path: str, range_header: str | None) -> Response:
        full_path = cls._normalize_path(full_path)

        if is_raw_filename(full_path):
            import io

            import rawpy
            from PIL import Image

            try:
                raw_data = await cls.read_file(full_path)
                with rawpy.imread(io.BytesIO(raw_data)) as raw:
                    rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
                im = Image.fromarray(rgb)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=90)
                content = buf.getvalue()
                return Response(content=content, media_type="image/jpeg")
            except FileNotFoundError:
                raise HTTPException(404, detail="File not found")
            except Exception as exc:
                raise HTTPException(500, detail=f"RAW file processing failed: {exc}")

        adapter_instance, adapter_model, root, rel = await cls.resolve_adapter_and_rel(full_path)
        redirect_response = await cls.maybe_redirect_download(adapter_instance, adapter_model, root, rel)
        if redirect_response is not None:
            return redirect_response

        try:
            content = await cls.read_file(full_path)
        except FileNotFoundError:
            raise HTTPException(404, detail="File not found")

        if not isinstance(content, (bytes, bytearray)):
            return Response(content=content, media_type="application/octet-stream")

        content_length = len(content)
        content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"

        if range_header:
            range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else content_length - 1

                start = max(0, min(start, content_length - 1))
                end = max(start, min(end, content_length - 1))

                chunk = content[start : end + 1]
                chunk_size = len(chunk)

                headers = {
                    "Content-Range": f"bytes {start}-{end}/{content_length}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(chunk_size),
                    "Content-Type": content_type,
                }

                return Response(content=chunk, status_code=206, headers=headers)

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": content_type,
        }

        if content_type.startswith("video/"):
            headers["Cache-Control"] = "public, max-age=3600"

        return Response(content=content, headers=headers)

    @classmethod
    async def get_thumbnail(cls, full_path: str, w: int, h: int, fit: str) -> Response:
        full_path = cls._normalize_path(full_path)
        if fit not in ("cover", "contain"):
            raise HTTPException(400, detail="fit must be cover|contain")
        adapter, mount, root, rel = await cls.resolve_adapter_and_rel(full_path)
        if not rel or rel.endswith("/"):
            raise HTTPException(400, detail="Not a file")
        if not (is_image_filename(rel) or is_video_filename(rel)):
            raise HTTPException(404, detail="Not an image or video")
        data, mime, key = await get_or_create_thumb(adapter, mount.id, root, rel, w, h, fit)  # type: ignore
        headers = {
            "Cache-Control": "public, max-age=3600",
            "ETag": key,
        }
        return Response(content=data, media_type=mime, headers=headers)

    @classmethod
    async def stream_response(cls, full_path: str, range_header: str | None):
        full_path = cls._normalize_path(full_path)
        try:
            return await cls.stream_file(full_path, range_header)
        except HTTPException:
            raise
        except FileNotFoundError:
            raise HTTPException(404, detail="File not found")
        except Exception as exc:
            raise HTTPException(500, detail=f"Stream error: {exc}")

    @classmethod
    async def create_temp_link(cls, full_path: str, expires_in: int):
        full_path = cls._normalize_path(full_path)
        token = await cls.generate_temp_link_token(full_path, expires_in=expires_in)
        file_domain = await ConfigService.get("FILE_DOMAIN")
        if file_domain:
            file_domain = file_domain.rstrip("/")
            url = f"{file_domain}/api/fs/public/{token}"
        else:
            url = f"/api/fs/public/{token}"
        return {"token": token, "path": full_path, "url": url}

    @classmethod
    async def access_public_file(cls, token: str, range_header: str | None):
        try:
            path = await cls.verify_temp_link_token(token)
        except HTTPException as exc:
            raise exc

        try:
            return await cls.stream_file(path, range_header)
        except FileNotFoundError:
            raise HTTPException(404, detail="File not found via token")
        except Exception as exc:
            raise HTTPException(500, detail=f"File access error: {exc}")

    @classmethod
    async def stat(cls, full_path: str):
        full_path = cls._normalize_path(full_path)
        return await cls.stat_file(full_path)

    @classmethod
    async def write_uploaded_file(cls, full_path: str, data: bytes):
        full_path = cls._normalize_path(full_path)
        await cls.write_file(full_path, data)
        return {"written": True, "path": full_path, "size": len(data)}

    @classmethod
    async def mkdir(cls, path: str):
        path = cls._normalize_path(path)
        if not path or path == "/":
            raise HTTPException(400, detail="Invalid path")
        await cls.make_dir(path)
        return {"created": True, "path": path}

    @classmethod
    async def move(cls, src: str, dst: str, overwrite: bool):
        src = cls._normalize_path(src)
        dst = cls._normalize_path(dst)
        debug_info = await cls.move_path(src, dst, overwrite=overwrite, return_debug=True, allow_cross=True)
        queued = bool(debug_info.get("queued"))
        response = {
            "moved": not queued,
            "queued": queued,
            "src": src,
            "dst": dst,
            "overwrite": overwrite,
        }
        if queued:
            response["task_id"] = debug_info.get("task_id")
            response["task_name"] = debug_info.get("task_name")
        return response

    @classmethod
    async def rename(cls, src: str, dst: str, overwrite: bool):
        src = cls._normalize_path(src)
        dst = cls._normalize_path(dst)
        await cls.rename_path(src, dst, overwrite=overwrite, return_debug=False)
        return {"renamed": True, "src": src, "dst": dst, "overwrite": overwrite}

    @classmethod
    async def copy(cls, src: str, dst: str, overwrite: bool):
        src = cls._normalize_path(src)
        dst = cls._normalize_path(dst)
        debug_info = await cls.copy_path(src, dst, overwrite=overwrite, return_debug=True, allow_cross=True)
        queued = bool(debug_info.get("queued"))
        response = {
            "copied": not queued,
            "queued": queued,
            "src": src,
            "dst": dst,
            "overwrite": overwrite,
        }
        if queued:
            response["task_id"] = debug_info.get("task_id")
            response["task_name"] = debug_info.get("task_name")
        return response

    @classmethod
    async def upload_stream_from_upload_file(cls, full_path: str, file: UploadFile, chunk_size: int, overwrite: bool):
        full_path = cls._normalize_path(full_path)
        if full_path.endswith("/"):
            raise HTTPException(400, detail="Path must be a file")
        adapter, _m, root, rel = await cls.resolve_adapter_and_rel(full_path)
        exists_func = getattr(adapter, "exists", None)
        if not overwrite and callable(exists_func):
            try:
                if await exists_func(root, rel):
                    raise HTTPException(409, detail="Destination exists")
            except HTTPException:
                raise
            except Exception:
                pass

        async def gen():
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        size = await cls.write_file_stream(full_path, gen(), overwrite=overwrite)
        return {"uploaded": True, "path": full_path, "size": size, "overwrite": overwrite}

    @classmethod
    async def list_directory(cls, full_path: str, page_num: int, page_size: int, sort_by: str, sort_order: str):
        full_path = cls._normalize_path(full_path)
        result = await cls.list_virtual_dir(full_path, page_num, page_size, sort_by, sort_order)
        return {
            "path": full_path,
            "entries": result["items"],
            "pagination": {
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "pages": result["pages"],
            },
        }

    @classmethod
    async def delete(cls, full_path: str):
        full_path = cls._normalize_path(full_path)
        await cls.delete_path(full_path)
        return {"deleted": True, "path": full_path}
