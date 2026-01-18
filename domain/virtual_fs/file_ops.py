import mimetypes
from typing import Any, AsyncIterator, Union

from fastapi import HTTPException
from fastapi.responses import Response

from domain.tasks import TaskService
from .thumbnail import is_raw_filename, raw_bytes_to_jpeg

from .listing import VirtualFSListingMixin


class VirtualFSFileOpsMixin(VirtualFSListingMixin):
    @classmethod
    def _normalize_written_result(
        cls,
        original_path: str,
        adapter_model: Any,
        result: Any,
        size_hint: int,
    ) -> tuple[str, int]:
        final_path = original_path
        size = size_hint
        if isinstance(result, dict):
            rel_override = result.get("rel")
            if isinstance(rel_override, str) and rel_override:
                final_path = cls._build_absolute_path(adapter_model.path, rel_override)
            else:
                path_override = result.get("path")
                if isinstance(path_override, str) and path_override:
                    final_path = cls._normalize_path(path_override)
            size_val = result.get("size")
            if isinstance(size_val, int):
                size = size_val
        return final_path, size

    @classmethod
    async def read_file(cls, path: str) -> Union[bytes, Any]:
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        if rel.endswith("/") or rel == "":
            raise HTTPException(400, detail="Path is a directory")
        read_func = await cls._ensure_method(adapter_instance, "read_file")
        return await read_func(root, rel)

    @classmethod
    async def write_file(cls, path: str, data: bytes):
        adapter_instance, adapter_model, root, rel = await cls.resolve_adapter_and_rel(path)
        if rel.endswith("/"):
            raise HTTPException(400, detail="Invalid file path")
        write_func = await cls._ensure_method(adapter_instance, "write_file")
        result = await write_func(root, rel, data)
        final_path, size = cls._normalize_written_result(path, adapter_model, result, len(data))
        await TaskService.trigger_tasks("file_written", final_path)
        return {"path": final_path, "size": size}

    @classmethod
    async def write_file_stream(cls, path: str, data_iter: AsyncIterator[bytes], overwrite: bool = True):
        adapter_instance, adapter_model, root, rel = await cls.resolve_adapter_and_rel(path)
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
            result = await stream_func(root, rel, data_iter)
            if isinstance(result, dict):
                size = int(result.get("size") or 0)
            else:
                size = int(result or 0)
        else:
            buf = bytearray()
            async for chunk in data_iter:
                if chunk:
                    buf.extend(chunk)
            write_func = await cls._ensure_method(adapter_instance, "write_file")
            result = await write_func(root, rel, bytes(buf))
            size = len(buf)

        final_path, size = cls._normalize_written_result(path, adapter_model, result, size)
        await TaskService.trigger_tasks("file_written", final_path)
        return {"path": final_path, "size": size}

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
    async def stream_file(cls, path: str, range_header: str | None):
        adapter_instance, adapter_model, root, rel = await cls.resolve_adapter_and_rel(path)
        if not rel or rel.endswith("/"):
            raise HTTPException(400, detail="Path is a directory")
        if is_raw_filename(rel):
            try:
                raw_data = await cls.read_file(path)
                content = raw_bytes_to_jpeg(raw_data, filename=rel)
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
