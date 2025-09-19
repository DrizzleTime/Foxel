from typing import Dict, Tuple, Any, Union, AsyncIterator, List
from fastapi import HTTPException
import mimetypes
from fastapi.responses import Response
import time
import hmac
import hashlib
import base64

from models import StorageAdapter
from .adapters.registry import runtime_registry
from api.response import page
from .thumbnail import is_image_filename, is_raw_filename
from services.processors.registry import get as get_processor
from services.tasks import task_service
from services.logging import LogService
from services.config import ConfigCenter


async def resolve_adapter_by_path(path: str) -> Tuple[StorageAdapter, str]:
    norm = path if path.startswith('/') else '/' + path
    adapters = await StorageAdapter.filter(enabled=True)
    best = None
    for a in adapters:
        if norm == a.path or norm.startswith(a.path.rstrip('/') + '/'):
            if (best is None) or len(a.path) > len(best.path):
                best = a
    if not best:
        raise HTTPException(404, detail="No storage adapter for path")
    rel = norm[len(best.path):].lstrip('/')
    return best, rel




async def resolve_adapter_and_rel(path: str):
    """返回 (adapter_instance, adapter_model, effective_root, rel_path)."""
    norm = path if path.startswith('/') else '/' + path
    try:
        adapter_model, rel = await resolve_adapter_by_path(norm)
    except HTTPException as e:
        raise e
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


async def _ensure_method(adapter: Any, method: str):
    func = getattr(adapter, method, None)
    if not callable(func):
        raise HTTPException(501, detail=f"Adapter does not implement {method}")
    return func


async def path_is_directory(path: str) -> bool:
    """判断给定路径是否为目录。"""
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    rel = rel.rstrip('/')
    if rel == '':
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


async def list_virtual_dir(path: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Dict:
    norm = (path if path.startswith('/') else '/' + path).rstrip('/') or '/'
    adapters = await StorageAdapter.filter(enabled=True)

    child_mount_entries = []
    norm_prefix = norm.rstrip('/')
    for a in adapters:
        if a.path == norm:
            continue
        if a.path.startswith(norm_prefix + '/'):
            tail = a.path[len(norm_prefix):].lstrip('/')
            if '/' not in tail:
                child_mount_entries.append(tail)
    child_mount_entries = sorted(set(child_mount_entries))

    try:
        adapter_model, rel = await resolve_adapter_by_path(norm)
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
        effective_root = ''
        rel = ''

    adapter_entries = []
    adapter_total = 0
    covered = set()

    if adapter_model and adapter_instance:
        list_dir = await _ensure_method(adapter_instance, "list_dir")
        try:
            adapter_entries, adapter_total = await list_dir(effective_root, rel, page_num, page_size, sort_by, sort_order)
        except NotADirectoryError:
            raise HTTPException(400, detail="Not a directory")

        for item in adapter_entries:
            covered.add(item["name"])

    mount_entries = []
    for name in child_mount_entries:
        if name not in covered:
            mount_entries.append({"name": name, "is_dir": True,
                                  "size": 0, "mtime": 0, "type": "mount", "is_image": False})

    for ent in adapter_entries:
        if not ent.get('is_dir'):
            ent['is_image'] = is_image_filename(ent['name'])
        else:
            ent['is_image'] = False

    all_entries = adapter_entries + mount_entries
    
    if mount_entries:
        reverse = sort_order.lower() == "desc"
        def get_sort_key(item):
            key = (not item.get("is_dir"),)
            sort_field = sort_by.lower()
            if sort_field == "name":
                key += (item["name"].lower(),)
            elif sort_field == "size":
                key += (item.get("size", 0),)
            elif sort_field == "mtime":
                key += (item.get("mtime", 0),)
            else:
                key += (item["name"].lower(),)
            return key
        all_entries.sort(key=get_sort_key, reverse=reverse)
        
        total_entries = adapter_total + len(mount_entries)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        page_entries = all_entries[start_idx:end_idx]
        return page(page_entries, total_entries, page_num, page_size)
    
    return page(adapter_entries, adapter_total, page_num, page_size)


async def read_file(path: str) -> Union[bytes, Any]:
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    if rel.endswith('/') or rel == '':
        raise HTTPException(400, detail="Path is a directory")
    read_func = await _ensure_method(adapter_instance, "read_file")
    return await read_func(root, rel)


async def write_file(path: str, data: bytes):
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    if rel.endswith('/'):
        raise HTTPException(400, detail="Invalid file path")
    write_func = await _ensure_method(adapter_instance, "write_file")
    await write_func(root, rel, data)
    await task_service.trigger_tasks("file_written", path)
    await LogService.action(
        "virtual_fs", f"Wrote file to {path}", details={"path": path, "size": len(data)}
    )


async def write_file_stream(path: str, data_iter: AsyncIterator[bytes], overwrite: bool = True):
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    if rel.endswith('/'):
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
        write_func = await _ensure_method(adapter_instance, "write_file")
        await write_func(root, rel, bytes(buf))
        size = len(buf)

    await task_service.trigger_tasks("file_written", path)
    await LogService.action(
        "virtual_fs",
        f"Wrote file stream to {path}",
        details={"path": path, "size": size},
    )
    return size


async def make_dir(path: str):
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    if not rel:
        raise HTTPException(400, detail="Cannot create root")
    mkdir_func = await _ensure_method(adapter_instance, "mkdir")
    await mkdir_func(root, rel)
    await LogService.action("virtual_fs", f"Created directory {path}", details={"path": path})


async def delete_path(path: str):
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    if not rel:
        raise HTTPException(400, detail="Cannot delete root")
    delete_func = await _ensure_method(adapter_instance, "delete")
    await delete_func(root, rel)
    await task_service.trigger_tasks("file_deleted", path)
    await LogService.action("virtual_fs", f"Deleted {path}", details={"path": path})


async def move_path(src: str, dst: str, overwrite: bool = False, return_debug: bool = True):
    adapter_s, adapter_model_s, root_s, rel_s = await resolve_adapter_and_rel(src)
    adapter_d, adapter_model_d, root_d, rel_d = await resolve_adapter_and_rel(dst)
    debug_info = {
        "src": src, "dst": dst,
        "rel_s": rel_s, "rel_d": rel_d,
        "root_s": root_s, "root_d": root_d,
        "overwrite": overwrite
    }
    if adapter_model_s.id != adapter_model_d.id:
        raise HTTPException(400, detail="Cross-adapter move not supported")
    if not rel_s:
        raise HTTPException(400, detail="Cannot move or rename mount root")
    if not rel_d:
        raise HTTPException(400, detail="Invalid destination")

    exists_func = getattr(adapter_s, "exists", None)
    stat_func = getattr(adapter_s, "stat_path", None)
    delete_func = await _ensure_method(adapter_s, "delete")
    move_func = await _ensure_method(adapter_s, "move")

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
            detail=f"Destination already exists(kind={kind}, fs_path={fs_path}, rel_d={rel_d}, overwrite={overwrite})"
        )
    if dst_exists and overwrite:
        try:
            await delete_func(root_s, rel_d)
            debug_info["pre_delete"] = "ok"
        except Exception as e:
            debug_info["pre_delete"] = f"error:{e}"
            raise HTTPException(
                500, detail=f"Pre-delete failed before overwrite: {e}")

    if rel_s == rel_d:
        debug_info["noop"] = True
        return debug_info if return_debug else None

    try:
        await move_func(root_s, rel_s, rel_d)
        debug_info["moved"] = True
    except FileNotFoundError:
        raise HTTPException(404, detail="Source not found")
    except FileExistsError:
        raise HTTPException(
            409, detail="Destination already exists (race condition after pre-check)")
    except IsADirectoryError:
        raise HTTPException(400, detail="Invalid directory operation")
    except Exception as e:
        raise HTTPException(500, detail=f"Move failed: {e}")

    await LogService.action(
        "virtual_fs", f"Moved {src} to {dst}", details=debug_info
    )
    return debug_info if return_debug else None


async def rename_path(src: str, dst: str, overwrite: bool = False, return_debug: bool = True):
    adapter_s, adapter_model_s, root_s, rel_s = await resolve_adapter_and_rel(src)
    adapter_d, adapter_model_d, root_d, rel_d = await resolve_adapter_and_rel(dst)
    debug_info = {
        "src": src, "dst": dst,
        "rel_s": rel_s, "rel_d": rel_d,
        "root_s": root_s, "root_d": root_d,
        "overwrite": overwrite
    }
    if adapter_model_s.id != adapter_model_d.id:
        raise HTTPException(400, detail="Cross-adapter rename not supported")
    if not rel_s:
        raise HTTPException(400, detail="Cannot rename mount root")
    if not rel_d:
        raise HTTPException(400, detail="Invalid destination")

    exists_func = getattr(adapter_s, "exists", None)
    stat_func = getattr(adapter_s, "stat_path", None)
    delete_func = await _ensure_method(adapter_s, "delete")
    rename_func = await _ensure_method(adapter_s, "rename")

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
            detail=f"Destination already exists(kind={kind}, fs_path={fs_path}, rel_d={rel_d}, overwrite={overwrite})"
        )
    if dst_exists and overwrite:
        try:
            await delete_func(root_s, rel_d)
            debug_info["pre_delete"] = "ok"
        except Exception as e:
            debug_info["pre_delete"] = f"error:{e}"
            raise HTTPException(
                500, detail=f"Pre-delete failed before overwrite: {e}")

    if rel_s == rel_d:
        debug_info["noop"] = True
        return debug_info if return_debug else None

    try:
        await rename_func(root_s, rel_s, rel_d)
        debug_info["renamed"] = True
    except FileNotFoundError:
        raise HTTPException(404, detail="Source not found")
    except FileExistsError:
        raise HTTPException(
            409, detail="Destination already exists (race condition after pre-check)")
    except IsADirectoryError:
        raise HTTPException(400, detail="Invalid directory operation")
    except Exception as e:
        raise HTTPException(500, detail=f"Rename failed: {e}")

    await LogService.action(
        "virtual_fs", f"Renamed {src} to {dst}", details=debug_info
    )
    return debug_info if return_debug else None


async def stream_file(path: str, range_header: str | None):
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    if not rel or rel.endswith('/'):
        raise HTTPException(400, detail="Path is a directory")
    if is_raw_filename(rel):
        import rawpy
        from PIL import Image
        import io
        try:
            raw_data = await read_file(path)
            try:
                import rawpy
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
            except Exception as e:
                print(f"rawpy processing failed: {e}")
                raise e

            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=90)
            content = buf.getvalue()
            return Response(content=content, media_type='image/jpeg')
        except Exception as e:
            raise HTTPException(500, detail=f"RAW file processing failed: {e}")

    stream_impl = getattr(adapter_instance, "stream_file", None)
    if callable(stream_impl):
        return await stream_impl(root, rel, range_header)
    data = await read_file(path)
    mime, _ = mimetypes.guess_type(rel)
    return Response(content=data, media_type=mime or "application/octet-stream")


async def stat_file(path: str):
    adapter_instance, _, root, rel = await resolve_adapter_and_rel(path)
    stat_func = getattr(adapter_instance, "stat_file", None)
    if not callable(stat_func):
        raise HTTPException(501, detail="Adapter does not implement stat_file")
    return await stat_func(root, rel)


async def copy_path(src: str, dst: str, overwrite: bool = False, return_debug: bool = True):
    adapter_s, adapter_model_s, root_s, rel_s = await resolve_adapter_and_rel(src)
    adapter_d, adapter_model_d, root_d, rel_d = await resolve_adapter_and_rel(dst)
    debug_info = {
        "src": src, "dst": dst,
        "rel_s": rel_s, "rel_d": rel_d,
        "root_s": root_s, "root_d": root_d,
        "overwrite": overwrite
    }
    if adapter_model_s.id != adapter_model_d.id:
        raise HTTPException(400, detail="Cross-adapter copy not supported")
    if not rel_s:
        raise HTTPException(400, detail="Cannot copy mount root")
    if not rel_d:
        raise HTTPException(400, detail="Invalid destination")

    exists_func = getattr(adapter_s, "exists", None)
    stat_func = getattr(adapter_s, "stat_path", None)
    delete_func = getattr(adapter_s, "delete", None)
    copy_func = await _ensure_method(adapter_s, "copy")

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
        except Exception as e:
            debug_info["pre_delete"] = f"error:{e}"
            raise HTTPException(500, detail=f"Pre-delete failed: {e}")

    if rel_s == rel_d:
        debug_info["noop"] = True
        return debug_info if return_debug else None

    try:
        await copy_func(root_s, rel_s, rel_d, overwrite=overwrite)
        debug_info["copied"] = True
    except FileNotFoundError:
        raise HTTPException(404, detail="Source not found")
    except FileExistsError:
        raise HTTPException(
            409, detail="Destination already exists (race condition)")
    except Exception as e:
        raise HTTPException(500, detail=f"Copy failed: {e}")

    await LogService.action(
        "virtual_fs", f"Copied {src} to {dst}", details=debug_info
    )
    return debug_info if return_debug else None


async def process_file(
    path: str,
    processor_type: str,
    config: dict,
    save_to: str | None = None,
    overwrite: bool = False,
) -> Any:
    """处理指定路径（文件或目录）。目录会递归处理其下所有文件。"""

    processor = get_processor(processor_type)
    if not processor:
        raise HTTPException(400, detail=f"Processor {processor_type} not found")

    actual_is_dir = await path_is_directory(path)

    supported_exts = getattr(processor, "supported_exts", None) or []
    allowed_exts = {
        str(ext).lower().lstrip('.')
        for ext in supported_exts
        if isinstance(ext, str)
    }

    def matches_extension(rel_path: str) -> bool:
        if not allowed_exts:
            return True
        if '.' not in rel_path:
            return '' in allowed_exts
        ext = rel_path.rsplit('.', 1)[-1].lower()
        return ext in allowed_exts or f'.{ext}' in allowed_exts

    def coerce_result_bytes(result: Any) -> bytes:
        if isinstance(result, Response):
            return result.body
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
        if isinstance(result, str):
            return result.encode('utf-8')
        raise HTTPException(500, detail="Processor must return bytes/Response when produces_file=True")

    def build_absolute_path(mount_path: str, rel_path: str) -> str:
        rel_norm = rel_path.lstrip('/')
        mount_norm = mount_path.rstrip('/')
        if not mount_norm:
            return '/' + rel_norm if rel_norm else '/'
        return f"{mount_norm}/{rel_norm}" if rel_norm else mount_norm

    if actual_is_dir:
        if save_to:
            raise HTTPException(400, detail="Directory processing does not support custom save_to path")
        if not overwrite:
            raise HTTPException(400, detail="Directory processing requires overwrite")

        adapter_instance, adapter_model, root, rel = await resolve_adapter_and_rel(path)
        rel = rel.rstrip('/')
        list_dir = await _ensure_method(adapter_instance, "list_dir")
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
                    data = await read_file(absolute_path)
                    result = await processor.process(data, absolute_path, config)
                    if getattr(processor, "produces_file", False):
                        result_bytes = coerce_result_bytes(result)
                        await write_file(absolute_path, result_bytes)
                    processed_count += 1

                if total is None or page * page_size >= total:
                    break
                page += 1

        return {"processed_files": processed_count}

    # 单文件处理
    data = await read_file(path)
    result = await processor.process(data, path, config)

    target_path = save_to
    if overwrite and not target_path:
        target_path = path

    if target_path and getattr(processor, "produces_file", False):
        result_bytes = coerce_result_bytes(result)
        await write_file(target_path, result_bytes)
        return {"saved_to": target_path}

    return result


async def get_temp_link_secret_key() -> bytes:
    """Get the secret key for temporary links."""
    return await ConfigCenter.get_secret_key(
        "TEMP_LINK_SECRET_KEY", None
    )


async def generate_temp_link_token(path: str, expires_in: int = 3600) -> str:
    """为文件路径生成一个有时效的令牌。expires_in <= 0 表示永久"""
    if expires_in <= 0:
        expiration_time = "0"
    else:
        expiration_time = str(int(time.time() + expires_in))

    message = f"{path}:{expiration_time}".encode('utf-8')
    secret_key = await get_temp_link_secret_key()
    signature = hmac.new(secret_key, message, hashlib.sha256).digest()

    token_data = f"{path}:{expiration_time}:{base64.urlsafe_b64encode(signature).decode('utf-8')}"
    return base64.urlsafe_b64encode(token_data.encode('utf-8')).decode('utf-8')


async def verify_temp_link_token(token: str) -> str:
    """验证令牌并返回文件路径，如果无效或过期则抛出异常"""
    try:
        decoded_token = base64.urlsafe_b64decode(token).decode('utf-8')
        path, expiration_time_str, signature_b64 = decoded_token.rsplit(':', 2)
        signature = base64.urlsafe_b64decode(signature_b64)
    except (ValueError, TypeError, base64.binascii.Error):
        raise HTTPException(status_code=400, detail="Invalid token format")

    if expiration_time_str != "0":
        expiration_time = int(expiration_time_str)
        if time.time() > expiration_time:
            raise HTTPException(status_code=410, detail="Link has expired")

    message = f"{path}:{expiration_time_str}".encode('utf-8')
    secret_key = await get_temp_link_secret_key()
    expected_signature = hmac.new(secret_key, message, hashlib.sha256).digest()

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    return path
