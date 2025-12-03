import datetime
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from application.auth.dependencies import get_current_active_user
from application.backup.dependencies import backup_service

router = APIRouter(
    prefix="/api/backup",
    tags=["Backup & Restore"],
    dependencies=[Depends(get_current_active_user)],
)

@router.get("/export", summary="导出全站数据")
async def export_backup():
    """
    生成并下载一个包含所有关键数据的JSON文件。
    """
    try:
        data = await backup_service.export_data()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        headers = {
            "Content-Disposition": f"attachment; filename=foxel_backup_{timestamp}.json"
        }
        return JSONResponse(content=data, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/import", summary="导入数据")
async def import_backup(file: UploadFile = File(...)):
    """
    从上传的JSON文件恢复数据。
    **警告**: 这将会覆盖所有现有数据！
    """

    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="无效的文件类型, 请上传 .json 文件")

    try:
        contents = await file.read()
        data = json.loads(contents)
    except Exception:
        raise HTTPException(status_code=400, detail="无法解析JSON文件")
    
    try:
        await backup_service.import_data(data)
        return {"message": "数据导入成功。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")
