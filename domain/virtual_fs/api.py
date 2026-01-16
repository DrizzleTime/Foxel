from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from .service import VirtualFSService
from .types import MkdirRequest, MoveRequest

router = APIRouter(prefix="/api/fs", tags=["virtual-fs"])


@router.get("/file/{full_path:path}")
@audit(action=AuditAction.DOWNLOAD, description="获取文件")
async def get_file(
    full_path: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return await VirtualFSService.serve_file(full_path, request.headers.get("Range"))


@router.get("/thumb/{full_path:path}")
@audit(action=AuditAction.READ, description="获取缩略图")
async def get_thumb(
    full_path: str,
    request: Request,
    w: int = Query(256, ge=8, le=1024),
    h: int = Query(256, ge=8, le=1024),
    fit: str = Query("cover"),
):
    return await VirtualFSService.get_thumbnail(full_path, w, h, fit)


@router.get("/stream/{full_path:path}")
@audit(action=AuditAction.DOWNLOAD, description="流式读取文件")
async def stream_endpoint(
    full_path: str,
    request: Request,
):
    return await VirtualFSService.stream_response(full_path, request.headers.get("Range"))


@router.get("/temp-link/{full_path:path}")
@audit(action=AuditAction.SHARE, description="创建临时链接")
async def get_temp_link(
    full_path: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    expires_in: int = Query(3600, description="有效时间(秒), 0或负数表示永久"),
):
    data = await VirtualFSService.create_temp_link(full_path, expires_in)
    return success(data)


@router.get("/public/{token}")
@audit(action=AuditAction.DOWNLOAD, description="访问临时链接文件")
async def access_public_file(
    token: str,
    request: Request,
):
    return await VirtualFSService.access_public_file(token, request.headers.get("Range"))


@router.get("/public/{token}/{filename}")
@audit(action=AuditAction.DOWNLOAD, description="访问临时链接文件")
async def access_public_file_with_name(
    token: str,
    filename: str,
    request: Request,
):
    return await VirtualFSService.access_public_file(token, request.headers.get("Range"))


@router.get("/stat/{full_path:path}")
@audit(action=AuditAction.READ, description="查看文件信息")
async def get_file_stat(
    full_path: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    stat = await VirtualFSService.stat(full_path)
    return success(stat)


@router.post("/file/{full_path:path}")
@audit(action=AuditAction.UPLOAD, description="上传文件")
async def put_file(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str,
    file: UploadFile = File(...),
):
    data = await file.read()
    result = await VirtualFSService.write_uploaded_file(full_path, data)
    return success(result)


@router.post("/mkdir")
@audit(action=AuditAction.CREATE, description="创建目录", body_fields=["path"])
async def api_mkdir(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MkdirRequest,
):
    result = await VirtualFSService.mkdir(body.path)
    return success(result)


@router.post("/move")
@audit(action=AuditAction.UPDATE, description="移动路径", body_fields=["src", "dst"])
async def api_move(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MoveRequest,
    overwrite: bool = Query(False, description="是否允许覆盖已存在目标"),
):
    result = await VirtualFSService.move(body.src, body.dst, overwrite)
    return success(result)


@router.post("/rename")
@audit(action=AuditAction.UPDATE, description="重命名路径", body_fields=["src", "dst"])
async def api_rename(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MoveRequest,
    overwrite: bool = Query(False, description="是否允许覆盖已存在目标"),
):
    result = await VirtualFSService.rename(body.src, body.dst, overwrite)
    return success(result)


@router.post("/copy")
@audit(action=AuditAction.CREATE, description="复制路径", body_fields=["src", "dst"])
async def api_copy(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    body: MoveRequest,
    overwrite: bool = Query(False, description="是否覆盖已存在目标"),
):
    result = await VirtualFSService.copy(body.src, body.dst, overwrite)
    return success(result)


@router.post("/upload/{full_path:path}")
@audit(action=AuditAction.UPLOAD, description="流式上传文件")
async def upload_stream(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str,
    file: UploadFile = File(...),
    overwrite: bool = Query(True, description="是否覆盖已存在文件"),
    chunk_size: int = Query(1024 * 1024, ge=8 * 1024, le=8 * 1024 * 1024, description="单次读取块大小"),
):
    result = await VirtualFSService.upload_stream_from_upload_file(full_path, file, chunk_size, overwrite)
    return success(result)


@router.get("/{full_path:path}")
@audit(action=AuditAction.READ, description="浏览目录")
async def browse_fs(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str,
    page_num: int = Query(1, alias="page", ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
    sort_by: str = Query("name", description="按字段排序: name, size, mtime"),
    sort_order: str = Query("asc", description="排序顺序: asc, desc"),
):
    data = await VirtualFSService.list_directory(full_path, page_num, page_size, sort_by, sort_order)
    return success(data)


@router.delete("/{full_path:path}")
@audit(action=AuditAction.DELETE, description="删除路径")
async def api_delete(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    full_path: str,
):
    result = await VirtualFSService.delete(full_path)
    return success(result)


@router.get("/")
@audit(action=AuditAction.READ, description="浏览根目录")
async def root_listing(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    page_num: int = Query(1, alias="page", ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
    sort_by: str = Query("name", description="按字段排序: name, size, mtime"),
    sort_order: str = Query("asc", description="排序顺序: asc, desc"),
):
    data = await VirtualFSService.list_directory("/", page_num, page_size, sort_by, sort_order)
    return success(data)
