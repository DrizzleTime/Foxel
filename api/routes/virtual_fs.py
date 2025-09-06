from fastapi import APIRouter, UploadFile, File, HTTPException, Response, Query, Request, Depends
import mimetypes
import re
from typing import Annotated

from services.auth import get_current_active_user, User
from services.virtual_fs import (
    list_virtual_dir,
    read_file,
    write_file,
    make_dir,
    delete_path,
    move_path,
    resolve_adapter_and_rel,
    stream_file,
    generate_temp_link_token,
    verify_temp_link_token,
)
from services.thumbnail import is_image_filename, get_or_create_thumb, is_raw_filename
from schemas import MkdirRequest, MoveRequest
from api.response import success
from services.config import ConfigCenter

router = APIRouter(prefix='/api/fs', tags=["virtual-fs"])


@router.get("/file/{full_path:path}")
async def get_file(
    full_path: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    full_path = '/' + full_path if not full_path.startswith('/') else full_path

    if is_raw_filename(full_path):
        import rawpy
        from PIL import Image
        import io
        try:
            raw_data = await read_file(full_path)
            with rawpy.imread(io.BytesIO(raw_data)) as raw:
                rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
            im = Image.fromarray(rgb)
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=90)
            content = buf.getvalue()
            return Response(content=content, media_type='image/jpeg')
        except FileNotFoundError:
            raise HTTPException(404, detail="File not found")
        except Exception as e:
            raise HTTPException(500, detail=f"RAW file processing failed: {e}")

    try:
        content = await read_file(full_path)
    except FileNotFoundError:
        raise HTTPException(404, detail="File not found")

    if not isinstance(content, (bytes, bytearray)):
        return Response(content=content, media_type="application/octet-stream")

    content_length = len(content)
    content_type = mimetypes.guess_type(
        full_path)[0] or "application/octet-stream"

    range_header = request.headers.get('Range')
    if range_header:
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(
                2) else content_length - 1

            start = max(0, min(start, content_length - 1))
            end = max(start, min(end, content_length - 1))

            chunk = content[start:end + 1]
            chunk_size = len(chunk)

            headers = {
                'Content-Range': f'bytes {start}-{end}/{content_length}',
                'Accept-Ranges': 'bytes',
                'Content-Length': str(chunk_size),
                'Content-Type': content_type,
            }

            return Response(
                content=chunk,
                status_code=206,
                headers=headers
            )

    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Length': str(content_length),
        'Content-Type': content_type,
    }

    if content_type.startswith('video/'):
        headers['Cache-Control'] = 'public, max-age=3600'

    return Response(content=content, headers=headers)


@router.get("/thumb/{full_path:path}")
async def get_thumb(
    full_path: str,
    w: int = Query(256, ge=8, le=1024),
    h: int = Query(256, ge=8, le=1024),
    fit: str = Query("cover"),
):
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    if fit not in ("cover", "contain"):
        raise HTTPException(400, detail="fit must be cover|contain")
    adapter, mount, root, rel = await resolve_adapter_and_rel(full_path)
    if not rel or rel.endswith('/'):
        raise HTTPException(400, detail="Not a file")
    if not is_image_filename(rel):
        raise HTTPException(404, detail="Not an image")
    # type: ignore
    data, mime, key = await get_or_create_thumb(adapter, mount.id, root, rel, w, h, fit)
    headers = {
        'Cache-Control': 'public, max-age=3600',
        'ETag': key,
    }
    return Response(content=data, media_type=mime, headers=headers)


@router.get("/stream/{full_path:path}")
async def stream_endpoint(
    full_path: str,
    request: Request,
):
    """支持 Range 的视频/大文件流式读取，优先使用底层适配器 Range 能力。"""
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    range_header = request.headers.get('Range')
    try:
        return await stream_file(full_path, range_header)
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(404, detail="File not found")
    except Exception as e:
        raise HTTPException(500, detail=f"Stream error: {e}")


@router.get("/temp-link/{full_path:path}")
async def get_temp_link(
    full_path: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    expires_in: int = Query(3600, description="有效时间(秒), 0或负数表示永久")
):
    """获取文件的临时公开访问令牌"""
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    token = await generate_temp_link_token(full_path, expires_in=expires_in)
    file_domain = await ConfigCenter.get("FILE_DOMAIN")
    if file_domain:
        file_domain = file_domain.rstrip('/')
        url = f"{file_domain}/api/fs/public/{token}"
    else:
        url = f"/api/fs/public/{token}"
    return success({"token": token, "path": full_path, "url": url})


@router.get("/public/{token}")
async def access_public_file(
    token: str,
    request: Request,
):
    """通过令牌公开访问文件，支持 Range 请求"""
    try:
        path = await verify_temp_link_token(token)
    except HTTPException as e:
        raise e

    range_header = request.headers.get('Range')
    try:
        return await stream_file(path, range_header)
    except FileNotFoundError:
        raise HTTPException(404, detail="File not found via token")
    except Exception as e:
        raise HTTPException(500, detail=f"File access error: {e}")


@router.get("/stat/{full_path:path}")
async def get_file_stat(
    full_path: str,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    from services.virtual_fs import stat_file
    stat = await stat_file(full_path)
    return success(stat)


@router.post("/file/{full_path:path}")
async def put_file(
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str,
    file: UploadFile = File(...)
):
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    data = await file.read()
    await write_file(full_path, data)
    return success({"written": True, "path": full_path, "size": len(data)})


@router.post("/mkdir")
async def api_mkdir(
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MkdirRequest
):
    path = body.path if body.path.startswith('/') else '/' + body.path
    if not path or path == '/':
        raise HTTPException(400, detail="Invalid path")
    await make_dir(path)
    return success({"created": True, "path": path})


@router.post("/move")
async def api_move(
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MoveRequest
):
    src = body.src if body.src.startswith('/') else '/' + body.src
    dst = body.dst if body.dst.startswith('/') else '/' + body.dst
    await move_path(src, dst)
    return success({"moved": True, "src": src, "dst": dst})


@router.post("/rename")
async def api_rename(
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MoveRequest,
    overwrite: bool = Query(False, description="是否允许覆盖已存在目标"),
    debug: bool = Query(False, description="返回调试信息")
):
    src = body.src if body.src.startswith('/') else '/' + body.src
    dst = body.dst if body.dst.startswith('/') else '/' + body.dst
    from services.virtual_fs import rename_path
    debug_info = await rename_path(src, dst, overwrite=overwrite, return_debug=debug)
    return success({
        "renamed": True,
        "src": src,
        "dst": dst,
        "overwrite": overwrite,
        **({"debug": debug_info} if debug else {})
    })


@router.post("/copy")
async def api_copy(
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MoveRequest,
    overwrite: bool = Query(False, description="是否覆盖已存在目标"),
    debug: bool = Query(False, description="返回调试信息")
):
    from services.virtual_fs import copy_path
    src = body.src if body.src.startswith('/') else '/' + body.src
    dst = body.dst if body.dst.startswith('/') else '/' + body.dst
    debug_info = await copy_path(src, dst, overwrite=overwrite, return_debug=debug)
    return success({
        "copied": True,
        "src": src,
        "dst": dst,
        "overwrite": overwrite,
        **({"debug": debug_info} if debug else {})
    })


@router.post("/upload/{full_path:path}")
async def upload_stream(
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str,
    file: UploadFile = File(...),
    overwrite: bool = Query(True, description="是否覆盖已存在文件"),
    chunk_size: int = Query(1024 * 1024, ge=8 * 1024,
                            le=8 * 1024 * 1024, description="单次读取块大小")
):
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    if full_path.endswith('/'):
        raise HTTPException(400, detail="Path must be a file")
    from services.virtual_fs import write_file_stream, resolve_adapter_and_rel
    adapter, _m, root, rel = await resolve_adapter_and_rel(full_path)
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
    size = await write_file_stream(full_path, gen(), overwrite=overwrite)
    return success({"uploaded": True, "path": full_path, "size": size, "overwrite": overwrite})


@router.get("/{full_path:path}")
async def browse_fs(
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str,
    page_num: int = Query(1, alias="page", ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
    sort_by: str = Query("name", description="排序字段: name, size, mtime, ctime"),
    sort_order: str = Query("asc", description="排序方向: asc, desc")
):
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    result = await list_virtual_dir(full_path, page_num, page_size, sort_by, sort_order)
    return success({
        "path": full_path,
        "entries": result["items"],
        "pagination": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "pages": result["pages"]
        }
    })


@router.delete("/{full_path:path}")
async def api_delete(
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str
):
    full_path = '/' + full_path if not full_path.startswith('/') else full_path
    await delete_path(full_path)
    return success({"deleted": True, "path": full_path})


@router.get("/")
async def root_listing(
    current_user: Annotated[User, Depends(get_current_active_user)],
    page_num: int = Query(1, alias="page", ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
    sort_by: str = Query("name", description="排序字段: name, size, mtime, ctime"),
    sort_order: str = Query("asc", description="排序方向: asc, desc")
):
    return await browse_fs("", page_num, page_size, sort_by, sort_order)
