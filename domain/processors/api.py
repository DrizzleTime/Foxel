from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission import require_path_permission
from domain.permission import require_system_permission
from domain.permission.service import PermissionService
from domain.permission.types import PathAction
from domain.permission.types import SystemPermission
from domain.processors.registry import get_config_schema
from .service import ProcessorService
from .types import (
    ProcessDirectoryRequest,
    ProcessRequest,
    UpdateSourceRequest,
)

router = APIRouter(prefix="/api/processors", tags=["processors"])


@router.get("")
@audit(action=AuditAction.READ, description="获取处理器列表")
async def list_processors(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = ProcessorService.list_processors()
    return success(data)


@router.post("/process")
@audit(
    action=AuditAction.CREATE,
    description="处理单个文件",
    body_fields=["path", "processor_type", "save_to", "overwrite"],
)
@require_path_permission(PathAction.READ, "req.path")
async def process_file_with_processor(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    req: ProcessRequest = Body(...),
):
    meta = get_config_schema(req.processor_type) or {}
    if meta.get("produces_file"):
        if req.overwrite:
            await PermissionService.require_path_permission(current_user.id, req.path, PathAction.WRITE)
        elif req.save_to:
            await PermissionService.require_path_permission(current_user.id, req.save_to, PathAction.WRITE)
    data = await ProcessorService.process_file(req)
    return success(data)


@router.post("/process-directory")
@audit(
    action=AuditAction.CREATE,
    description="批量处理目录",
    body_fields=["path", "processor_type", "overwrite", "max_depth", "suffix"],
)
@require_path_permission(PathAction.READ, "req.path")
async def process_directory_with_processor(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    req: ProcessDirectoryRequest = Body(...),
):
    meta = get_config_schema(req.processor_type) or {}
    if meta.get("produces_file"):
        await PermissionService.require_path_permission(current_user.id, req.path, PathAction.WRITE)
    data = await ProcessorService.process_directory(req)
    return success(data)


@router.get("/source/{processor_type}")
@audit(action=AuditAction.READ, description="获取处理器源码")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def get_processor_source(
    request: Request,
    processor_type: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await ProcessorService.get_source(processor_type)
    return success(data)


@router.put("/source/{processor_type}")
@audit(action=AuditAction.UPDATE, description="更新处理器源码")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def update_processor_source(
    request: Request,
    processor_type: str,
    req: UpdateSourceRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await ProcessorService.update_source(processor_type, req)
    return success(data)


@router.post("/reload")
@audit(action=AuditAction.UPDATE, description="重载处理器模块")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def reload_processor_modules(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = ProcessorService.reload()
    return success(data)
