from __future__ import annotations
import asyncio
import inspect
import io
import hashlib
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif", "bmp",
               "tiff", "arw", "cr2", "cr3", "nef", "rw2", "orf", "pef", "dng"}
RAW_EXT = {"arw", "cr2", "cr3", "nef", "rw2", "orf", "pef", "dng"}
VIDEO_EXT = {"mp4", "mov", "m4v", "avi", "mkv", "wmv", "flv", "webm", "mpg", "mpeg", "3gp"}
MAX_IMAGE_SOURCE_SIZE = 200 * 1024 * 1024
VIDEO_RANGE_LIMIT = 16 * 1024 * 1024  # 16MB
VIDEO_INITIAL_CHUNK = 4 * 1024 * 1024
CACHE_ROOT = Path('data/.thumb_cache')


def is_image_filename(name: str) -> bool:
    parts = name.rsplit('.', 1)
    if len(parts) < 2:
        return False
    return parts[1].lower() in ALLOWED_EXT


def is_raw_filename(name: str) -> bool:
    parts = name.rsplit('.', 1)
    if len(parts) < 2:
        return False
    return parts[1].lower() in RAW_EXT


def is_video_filename(name: str) -> bool:
    parts = name.rsplit('.', 1)
    if len(parts) < 2:
        return False
    return parts[1].lower() in VIDEO_EXT


def _cache_key(adapter_id: int, rel: str, size: int, mtime: int, w: int, h: int, fit: str) -> str:
    raw = f"{adapter_id}|{rel}|{size}|{mtime}|{w}x{h}|{fit}".encode()
    return hashlib.sha1(raw).hexdigest()


def _cache_path(key: str) -> Path:
    sub = Path(key[:2]) / key[2:4]
    return CACHE_ROOT / sub / f"{key}.webp"


def _ensure_cache_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def _image_to_webp(im, w: int, h: int, fit: str) -> Tuple[bytes, str]:
    from PIL import Image
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if im.mode in ("P", "LA") else "RGB")
    if fit == 'cover':
        im_ratio = im.width / im.height
        target_ratio = w / h
        if im_ratio > target_ratio:
            new_h = h
            new_w = int(h * im_ratio)
        else:
            new_w = w
            new_h = int(w / im_ratio)
        im = im.resize((new_w, new_h))
        left = max(0, (im.width - w)//2)
        top = max(0, (im.height - h)//2)
        im = im.crop((left, top, left + w, top + h))
    else:
        im.thumbnail((w, h))
    buf = io.BytesIO()
    im.save(buf, 'WEBP', quality=80)
    return buf.getvalue(), 'image/webp'


def generate_thumb(data: bytes, w: int, h: int, fit: str, is_raw: bool = False) -> Tuple[bytes, str]:
    from PIL import Image
    if is_raw:
        try:
            import rawpy
            with rawpy.imread(io.BytesIO(data)) as raw:
                try:
                    thumb = raw.extract_thumb()
                except rawpy.LibRawNoThumbnailError:
                    thumb = None

                if thumb is not None and thumb.format in [rawpy.ThumbFormat.JPEG, rawpy.ThumbFormat.BITMAP]:
                    im = Image.open(io.BytesIO(thumb.data))
                else:
                    rgb = raw.postprocess(
                        use_camera_wb=False, use_auto_wb=True, output_bps=8)
                    im = Image.fromarray(rgb)
        except Exception as e:
            print(f"rawpy processing failed: {e}")
            raise e

    else:
        im = Image.open(io.BytesIO(data))

    return _image_to_webp(im, w, h, fit)


async def _collect_response_bytes(response, limit: int) -> bytes:
    if response is None:
        return b""

    try:
        if isinstance(response, (bytes, bytearray)):
            return bytes(response[:limit])

        body = getattr(response, "body", None)
        if body is not None:
            return bytes(body[:limit])

        iterator = getattr(response, "body_iterator", None)
        if iterator is not None:
            data = bytearray()
            async for chunk in iterator:
                if not chunk:
                    continue
                need = limit - len(data)
                if need <= 0:
                    break
                data.extend(chunk[:need])
                if len(data) >= limit:
                    break
            return bytes(data)

        if hasattr(response, "__aiter__"):
            data = bytearray()
            async for chunk in response:
                if not chunk:
                    continue
                need = limit - len(data)
                if need <= 0:
                    break
                data.extend(chunk[:need])
                if len(data) >= limit:
                    break
            return bytes(data)
    finally:
        close_func = getattr(response, "close", None)
        if callable(close_func):
            result = close_func()
            if inspect.isawaitable(result):
                await result

    return b""


async def _read_range_slice(adapter, root: str, rel: str, start: int, end: int) -> bytes:
    read_range = getattr(adapter, "read_file_range", None)
    if callable(read_range):
        try:
            return await read_range(root, rel, start, end)
        except TypeError:
            return await read_range(root, rel, start, end=end)

    stream_impl = getattr(adapter, "stream_file", None)
    if callable(stream_impl):
        range_header = f"bytes={start}-{end}"
        response = await stream_impl(root, rel, range_header)
        expected = end - start + 1
        return await _collect_response_bytes(response, expected)

    read_file = getattr(adapter, "read_file", None)
    if callable(read_file) and start == 0:
        data = await read_file(root, rel)
        slice_end = end + 1
        return data[:slice_end]

    return b""


async def _read_video_prefix(adapter, root: str, rel: str, size: int, limit: int = VIDEO_RANGE_LIMIT) -> bytes:
    chunk_size = min(VIDEO_INITIAL_CHUNK, limit)
    offset = 0
    collected = bytearray()

    while len(collected) < limit:
        end = offset + chunk_size - 1
        data = await _read_range_slice(adapter, root, rel, offset, end)
        if not data:
            break
        collected.extend(data)
        if len(data) < chunk_size:
            break
        offset += len(data)
        remaining = limit - len(collected)
        if remaining <= 0:
            break
        chunk_size = min(chunk_size * 2, remaining)

    if not collected and size <= limit:
        read_file = getattr(adapter, "read_file", None)
        if callable(read_file):
            blob = await read_file(root, rel)
            if blob:
                return bytes(blob[:limit])

    return bytes(collected[:limit])


async def _run_ffmpeg_extract_frame(src_path: str, dst_path: str):
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", src_path,
        "-frames:v", "1",
        dst_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise RuntimeError("未找到 ffmpeg，可执行文件需要在 PATH 中") from e

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        message = stderr.decode().strip() or stdout.decode().strip() or "ffmpeg 执行失败"
        raise RuntimeError(message)


async def _generate_video_thumb(video_bytes: bytes, rel: str, w: int, h: int, fit: str) -> Tuple[bytes, str]:
    from PIL import Image

    suffix = Path(rel).suffix or ".mp4"
    src_tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    src_path = src_tmp.name
    try:
        src_tmp.write(video_bytes)
        src_tmp.flush()
    finally:
        src_tmp.close()

    dst_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    dst_path = dst_tmp.name
    dst_tmp.close()

    try:
        await _run_ffmpeg_extract_frame(src_path, dst_path)
        with Image.open(dst_path) as im:
            im.load()
            return _image_to_webp(im, w, h, fit)
    finally:
        with suppress(FileNotFoundError):
            Path(src_path).unlink()
        with suppress(FileNotFoundError):
            Path(dst_path).unlink()


async def get_or_create_thumb(adapter, adapter_id: int, root: str, rel: str, w: int, h: int, fit: str = 'cover'):
    stat = await adapter.stat_file(root, rel)
    size = int(stat.get('size') or 0)
    is_video = is_video_filename(rel)
    if not is_video and size > MAX_IMAGE_SOURCE_SIZE:
        raise HTTPException(400, detail="Image too large for thumbnail")

    key = _cache_key(adapter_id, rel, size, int(
        stat.get('mtime', 0)), w, h, fit)
    path = _cache_path(key)
    if path.exists():
        return path.read_bytes(), 'image/webp', key

    _ensure_cache_dir(path)
    thumb_bytes, mime = None, None

    get_thumb_impl = getattr(adapter, "get_thumbnail", None)
    if callable(get_thumb_impl):
        size_str = "large" if w > 400 else "medium" if w > 100 else "small"
        native_thumb_bytes = await get_thumb_impl(root, rel, size_str)

        if native_thumb_bytes:
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(native_thumb_bytes))
                buf = io.BytesIO()
                im.save(buf, 'WEBP', quality=85)
                thumb_bytes = buf.getvalue()
                mime = 'image/webp'
            except Exception as e:
                print(
                    f"Failed to convert native thumbnail to WebP: {e}, falling back.")
                thumb_bytes, mime = None, None

    if not thumb_bytes:
        if is_video:
            try:
                video_bytes = await _read_video_prefix(adapter, root, rel, size)
            except HTTPException:
                raise
            except Exception as e:
                print(f"Video prefix read failed: {e}")
                raise HTTPException(500, detail=f"Video read failed: {e}")

            if not video_bytes:
                raise HTTPException(500, detail="Unable to read video data for thumbnail")

            try:
                thumb_bytes, mime = await _generate_video_thumb(video_bytes, rel, w, h, fit)
            except Exception as e:
                print(f"Video thumbnail generation failed: {e}")
                raise HTTPException(
                    500, detail=f"Video thumbnail generation failed: {e}")
        else:
            read_data = await adapter.read_file(root, rel)
            try:
                thumb_bytes, mime = generate_thumb(
                    read_data, w, h, fit, is_raw=is_raw_filename(rel))
            except Exception as e:
                print(e)
                raise HTTPException(
                    500, detail=f"Thumbnail generation failed: {e}")

    if thumb_bytes:
        path.write_bytes(thumb_bytes)
        return thumb_bytes, mime, key

    raise HTTPException(
        500, detail="Failed to generate thumbnail by any means")
