from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.response import success
from application.auth.dependencies import User, get_current_active_user
from application.vector_db.dependencies import vector_db_use_cases
from models.database import UserAccount

router = APIRouter(prefix="/api/vector-db", tags=["vector-db"])


class VectorDBConfigPayload(BaseModel):
    type: str = Field(..., description="向量数据库提供者类型")
    config: Dict[str, Any] = Field(default_factory=dict, description="提供者配置参数")


@router.post("/clear-all", summary="清空向量数据库")
async def clear_vector_db(user: User = Depends(get_current_active_user)):
    try:
        await vector_db_use_cases.clear_all_data()
        return success(msg="向量数据库已清空")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", summary="获取向量数据库统计")
async def get_vector_db_stats(user: User = Depends(get_current_active_user)):
    try:
        data = await vector_db_use_cases.get_all_stats()
        return success(data=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers", summary="列出可用向量数据库提供者")
async def list_vector_providers(user: User = Depends(get_current_active_user)):
    return success(await vector_db_use_cases.list_providers())


@router.get("/config", summary="获取当前向量数据库配置")
async def get_vector_db_config(user: UserAccount = Depends(get_current_active_user)):
    data = await vector_db_use_cases.current_provider()
    return success(data)


@router.post("/config", summary="更新向量数据库配置")
async def update_vector_db_config(
    payload: VectorDBConfigPayload, user: UserAccount = Depends(get_current_active_user)
):
    try:
        await vector_db_use_cases.update_config(payload.type, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    config_data = await vector_db_use_cases.current_provider()
    stats = await vector_db_use_cases.get_all_stats()
    return success({"config": config_data, "stats": stats})
