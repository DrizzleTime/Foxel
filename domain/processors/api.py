from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth.service import get_current_active_user
from domain.auth.types import User
from domain.processors.service import ProcessorService
from domain.processors.types import (
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
async def process_file_with_processor(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    req: ProcessRequest = Body(...),
):
    data = await ProcessorService.process_file(req)
    return success(data)


@router.post("/process-directory")
@audit(
    action=AuditAction.CREATE,
    description="批量处理目录",
    body_fields=["path", "processor_type", "overwrite", "max_depth", "suffix"],
)
async def process_directory_with_processor(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    req: ProcessDirectoryRequest = Body(...),
):
    data = await ProcessorService.process_directory(req)
    return success(data)


@router.get("/source/{processor_type}")
@audit(action=AuditAction.READ, description="获取处理器源码")
async def get_processor_source(
    request: Request,
    processor_type: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await ProcessorService.get_source(processor_type)
    return success(data)


@router.put("/source/{processor_type}")
@audit(action=AuditAction.UPDATE, description="更新处理器源码")
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
async def reload_processor_modules(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = ProcessorService.reload()
    return success(data)
