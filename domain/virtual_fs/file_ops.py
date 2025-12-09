from __future__ import annotations

import mimetypes
from typing import Any, AsyncIterator, Union

from fastapi import HTTPException
from fastapi.responses import Response

from domain.tasks.service import TaskService
from domain.virtual_fs.thumbnail import is_raw_filename

from .listing import VirtualFSListingMixin


class VirtualFSFileOpsMixin(VirtualFSListingMixin):
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
