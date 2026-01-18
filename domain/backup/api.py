import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from domain.audit import AuditAction, audit
from domain.auth import get_current_active_user
from .service import BackupService

router = APIRouter(
    prefix="/api/backup",
    tags=["Backup & Restore"],
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/export", summary="导出全站数据")
@audit(action=AuditAction.DOWNLOAD, description="导出备份")
async def export_backup(
    request: Request, sections: list[str] | None = Query(default=None)
):
    data = await BackupService.export_data(sections=sections)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    headers = {"Content-Disposition": f"attachment; filename=foxel_backup_{timestamp}.json"}
    return JSONResponse(content=data.model_dump(), headers=headers)


@router.post("/import", summary="导入数据")
@audit(action=AuditAction.UPLOAD, description="导入备份")
async def import_backup(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("replace"),
):
    await BackupService.import_from_bytes(file.filename, await file.read(), mode=mode)
    return {"message": "数据导入成功。"}
