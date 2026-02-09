import mimetypes
import re
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from fastapi.responses import Response

from domain.config import ConfigService
from domain.tasks import TaskService
from .thumbnail import (
    get_or_create_thumb,
    is_image_filename,
    is_raw_filename,
    is_video_filename,
    raw_bytes_to_jpeg,
)

from .temp_link import VirtualFSTempLinkMixin


class VirtualFSRouteMixin(VirtualFSTempLinkMixin):
    @classmethod
    async def serve_file(cls, full_path: str, range_header: str | None) -> Response:
        full_path = cls._normalize_path(full_path)

        if is_raw_filename(full_path):
            try:
                raw_data = await cls.read_file(full_path)
                content = raw_bytes_to_jpeg(raw_data, filename=full_path)
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
            range_match = re.match(r"bytes=(\\d+)-(\\d*)", range_header)
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
        filename = full_path.rstrip("/").split("/")[-1]
        filename_part = f"/{quote(filename, safe='')}" if filename else ""
        file_domain = await ConfigService.get("FILE_DOMAIN")
        if file_domain:
            file_domain = file_domain.rstrip("/")
            url = f"{file_domain}/api/fs/public/{token}{filename_part}"
        else:
            url = f"/api/fs/public/{token}{filename_part}"
        return {"token": token, "path": full_path, "url": url}

    @classmethod
    async def access_public_file(cls, token: str, range_header: str | None):
        try:
            path = await cls.verify_temp_link_token(token)
        except HTTPException as exc:
            raise exc

        try:
            response = await cls.stream_file(path, range_header)
        except FileNotFoundError:
            raise HTTPException(404, detail="File not found via token")
        except Exception as exc:
            raise HTTPException(500, detail=f"File access error: {exc}")

        filename = path.rstrip("/").split("/")[-1]
        if filename and not response.headers.get("Content-Disposition"):
            response.headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(filename, safe='')}"
        return response

    @classmethod
    async def stat(cls, full_path: str):
        full_path = cls._normalize_path(full_path)
        return await cls.stat_file(full_path)

    @classmethod
    async def write_uploaded_file(cls, full_path: str, data: bytes):
        full_path = cls._normalize_path(full_path)
        result = await cls.write_file(full_path, data)
        path = full_path
        size = len(data)
        if isinstance(result, dict):
            path = result.get("path") or path
            size_val = result.get("size")
            if isinstance(size_val, int):
                size = size_val
        return {"written": True, "path": path, "size": size}

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
        adapter, adapter_model, root, rel = await cls.resolve_adapter_and_rel(full_path)
        exists_func = getattr(adapter, "exists", None)
        if not overwrite and callable(exists_func):
            try:
                if await exists_func(root, rel):
                    raise HTTPException(409, detail="Destination exists")
            except HTTPException:
                raise
            except Exception:
                pass

        upload_func = getattr(adapter, "write_upload_file", None)
        if callable(upload_func):
            try:
                await file.seek(0)
            except Exception:
                pass
            size_hint = getattr(file, "size", None)
            if not isinstance(size_hint, int):
                size_hint = None
            filename = file.filename or (rel.rsplit("/", 1)[-1] if rel else "file")
            result = await upload_func(root, rel, file.file, filename, size_hint, file.content_type)
            final_path, size = cls._normalize_written_result(full_path, adapter_model, result, size_hint or 0)
            await TaskService.trigger_tasks("file_written", final_path)
            return {"uploaded": True, "path": final_path, "size": size, "overwrite": overwrite}

        async def gen():
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        result = await cls.write_file_stream(full_path, gen(), overwrite=overwrite)
        path = full_path
        size = 0
        if isinstance(result, dict):
            path = result.get("path") or path
            size_val = result.get("size")
            if isinstance(size_val, int):
                size = size_val
        else:
            size = int(result or 0)
        return {"uploaded": True, "path": path, "size": size, "overwrite": overwrite}

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
