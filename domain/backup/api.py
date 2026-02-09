import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission import require_system_permission
from domain.permission.types import SystemPermission
from .service import BackupService

router = APIRouter(
    prefix="/api/backup",
    tags=["Backup & Restore"],
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/export", summary="导出全站数据")
@audit(action=AuditAction.DOWNLOAD, description="导出备份")
@require_system_permission(SystemPermission.CONFIG_EDIT)
async def export_backup(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    sections: list[str] | None = Query(default=None),
):
    data = await BackupService.export_data(sections=sections)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    headers = {"Content-Disposition": f"attachment; filename=foxel_backup_{timestamp}.json"}
    return JSONResponse(content=data.model_dump(mode="json"), headers=headers)


@router.post("/import", summary="导入数据")
@audit(action=AuditAction.UPLOAD, description="导入备份")
@require_system_permission(SystemPermission.CONFIG_EDIT)
async def import_backup(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
    mode: str = Form("replace"),
):
    await BackupService.import_from_bytes(file.filename, await file.read(), mode=mode)
    return {"message": "数据导入成功。"}
