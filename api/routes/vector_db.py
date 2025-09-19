from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.auth import get_current_active_user
from models.database import UserAccount
from services.vector_db import (
    VectorDBService,
    VectorDBConfigManager,
    list_providers,
    get_provider_entry,
)
from services.vector_db.providers import get_provider_class
from api.response import success

router = APIRouter(prefix="/api/vector-db", tags=["vector-db"])


class VectorDBConfigPayload(BaseModel):
    type: str = Field(..., description="向量数据库提供者类型")
    config: Dict[str, Any] = Field(default_factory=dict, description="提供者配置参数")


@router.post("/clear-all", summary="清空向量数据库")
async def clear_vector_db(user: UserAccount = Depends(get_current_active_user)):
    if user.username != 'admin':
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    try:
        service = VectorDBService()
        await service.clear_all_data()
        return success(msg="向量数据库已清空")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", summary="获取向量数据库统计")
async def get_vector_db_stats(user: UserAccount = Depends(get_current_active_user)):
    if user.username != 'admin':
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    try:
        service = VectorDBService()
        data = await service.get_all_stats()
        return success(data=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers", summary="列出可用向量数据库提供者")
async def list_vector_providers(user: UserAccount = Depends(get_current_active_user)):
    if user.username != 'admin':
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    return success(list_providers())


@router.get("/config", summary="获取当前向量数据库配置")
async def get_vector_db_config(user: UserAccount = Depends(get_current_active_user)):
    if user.username != 'admin':
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    service = VectorDBService()
    data = await service.current_provider()
    return success(data)


@router.post("/config", summary="更新向量数据库配置")
async def update_vector_db_config(payload: VectorDBConfigPayload, user: UserAccount = Depends(get_current_active_user)):
    if user.username != 'admin':
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    entry = get_provider_entry(payload.type)
    if not entry:
        raise HTTPException(status_code=400, detail=f"未知的向量数据库类型: {payload.type}")
    if not entry.get("enabled", True):
        raise HTTPException(status_code=400, detail="该向量数据库类型暂不可用")

    provider_cls = get_provider_class(payload.type)
    if not provider_cls:
        raise HTTPException(status_code=400, detail=f"未找到类型 {payload.type} 对应的实现")

    # 先尝试建立连接，确保配置有效
    test_provider = provider_cls(payload.config)
    try:
        await test_provider.initialize()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        client = getattr(test_provider, "client", None)
        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass

    await VectorDBConfigManager.save_config(payload.type, payload.config)
    service = VectorDBService()
    await service.reload()
    config_data = await service.current_provider()
    stats = await service.get_all_stats()
    return success({"config": config_data, "stats": stats})
