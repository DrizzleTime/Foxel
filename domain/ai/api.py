from typing import Annotated, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.ai.service import AIProviderService, VectorDBConfigManager, VectorDBService
from domain.ai.types import (
    AIDefaultsUpdate,
    AIModelCreate,
    AIModelUpdate,
    AIProviderCreate,
    AIProviderUpdate,
    VectorDBConfigPayload,
)
from domain.ai.vector_providers import get_provider_class, get_provider_entry, list_providers
from domain.auth.service import get_current_active_user
from domain.auth.types import User

router_ai = APIRouter(prefix="/api/ai", tags=["ai"])
router_vector_db = APIRouter(prefix="/api/vector-db", tags=["vector-db"])


@audit(action=AuditAction.READ, description="获取 AI 提供商列表")
@router_ai.get("/providers")
async def list_providers_endpoint(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    providers = await AIProviderService.list_providers()
    return success({"providers": providers})


@audit(
    action=AuditAction.CREATE,
    description="创建 AI 提供商",
    body_fields=["name", "identifier", "provider_type", "api_format", "base_url", "logo_url"],
    redact_fields=["api_key"],
)
@router_ai.post("/providers")
async def create_provider(
    request: Request,
    payload: AIProviderCreate,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    provider = await AIProviderService.create_provider(payload.dict())
    return success(provider)


@audit(action=AuditAction.READ, description="获取 AI 提供商详情")
@router_ai.get("/providers/{provider_id}")
async def get_provider(
    request: Request,
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    provider = await AIProviderService.get_provider(provider_id, with_models=True)
    return success(provider)


@audit(
    action=AuditAction.UPDATE,
    description="更新 AI 提供商",
    body_fields=["name", "provider_type", "api_format", "base_url", "logo_url", "api_key"],
    redact_fields=["api_key"],
)
@router_ai.put("/providers/{provider_id}")
async def update_provider(
    request: Request,
    provider_id: Annotated[int, Path(..., gt=0)],
    payload: AIProviderUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    provider = await AIProviderService.update_provider(provider_id, data)
    return success(provider)


@audit(action=AuditAction.DELETE, description="删除 AI 提供商")
@router_ai.delete("/providers/{provider_id}")
async def delete_provider(
    request: Request,
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    await AIProviderService.delete_provider(provider_id)
    return success({"id": provider_id})


@audit(action=AuditAction.UPDATE, description="同步模型列表")
@router_ai.post("/providers/{provider_id}/sync-models")
async def sync_models(
    request: Request,
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        result = await AIProviderService.sync_models(provider_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise HTTPException(status_code=502, detail=f"Failed to synchronize models: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return success(result)


@audit(action=AuditAction.READ, description="获取远程模型列表")
@router_ai.get("/providers/{provider_id}/remote-models")
async def fetch_remote_models(
    request: Request,
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        models = await AIProviderService.fetch_remote_models(provider_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise HTTPException(status_code=502, detail=f"Failed to pull models: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return success({"models": models})


@audit(action=AuditAction.READ, description="获取模型列表")
@router_ai.get("/providers/{provider_id}/models")
async def list_models(
    request: Request,
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    models = await AIProviderService.list_models(provider_id)
    return success({"models": models})


@audit(
    action=AuditAction.CREATE,
    description="创建模型",
    body_fields=["name", "display_name", "capabilities", "context_window", "embedding_dimensions"],
)
@router_ai.post("/providers/{provider_id}/models")
async def create_model(
    request: Request,
    provider_id: Annotated[int, Path(..., gt=0)],
    payload: AIModelCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    model = await AIProviderService.create_model(provider_id, payload.dict())
    return success(model)


@audit(
    action=AuditAction.UPDATE,
    description="更新模型",
    body_fields=["display_name", "description", "capabilities", "context_window", "embedding_dimensions"],
)
@router_ai.put("/models/{model_id}")
async def update_model(
    request: Request,
    model_id: Annotated[int, Path(..., gt=0)],
    payload: AIModelUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    model = await AIProviderService.update_model(model_id, data)
    return success(model)


@audit(action=AuditAction.DELETE, description="删除模型")
@router_ai.delete("/models/{model_id}")
async def delete_model(
    request: Request,
    model_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    await AIProviderService.delete_model(model_id)
    return success({"id": model_id})


def _get_embedding_dimension(entry: Optional[Dict]) -> Optional[int]:
    if not entry:
        return None
    value = entry.get("embedding_dimensions")
    return int(value) if value is not None else None


@audit(action=AuditAction.READ, description="获取默认模型")
@router_ai.get("/defaults")
async def get_defaults(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    defaults = await AIProviderService.get_default_models()
    return success(defaults)


@audit(
    action=AuditAction.UPDATE,
    description="更新默认模型",
    body_fields=["chat", "vision", "embedding", "rerank", "voice", "tools"],
)
@router_ai.put("/defaults")
async def update_defaults(
    request: Request,
    payload: AIDefaultsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    previous = await AIProviderService.get_default_models()
    try:
        updated = await AIProviderService.set_default_models(payload.as_mapping())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prev_dim = _get_embedding_dimension(previous.get("embedding"))
    next_dim = _get_embedding_dimension(updated.get("embedding"))

    if prev_dim and next_dim and prev_dim != next_dim:
        try:
            await VectorDBService().clear_all_data()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to clear vector database: {exc}") from exc

    return success(updated)


@audit(action=AuditAction.UPDATE, description="清空向量数据库")
@router_vector_db.post("/clear-all", summary="清空向量数据库")
async def clear_vector_db(request: Request, user: User = Depends(get_current_active_user)):
    try:
        service = VectorDBService()
        await service.clear_all_data()
        return success(msg="向量数据库已清空")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@audit(action=AuditAction.READ, description="获取向量数据库统计")
@router_vector_db.get("/stats", summary="获取向量数据库统计")
async def get_vector_db_stats(request: Request, user: User = Depends(get_current_active_user)):
    try:
        service = VectorDBService()
        data = await service.get_all_stats()
        return success(data=data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@audit(action=AuditAction.READ, description="获取向量数据库提供者列表")
@router_vector_db.get("/providers", summary="列出可用向量数据库提供者")
async def list_vector_providers(request: Request, user: User = Depends(get_current_active_user)):
    return success(list_providers())


@audit(action=AuditAction.READ, description="获取向量数据库配置")
@router_vector_db.get("/config", summary="获取当前向量数据库配置")
async def get_vector_db_config(request: Request, user: User = Depends(get_current_active_user)):
    service = VectorDBService()
    data = await service.current_provider()
    return success(data)


@audit(action=AuditAction.UPDATE, description="更新向量数据库配置", body_fields=["type"])
@router_vector_db.post("/config", summary="更新向量数据库配置")
async def update_vector_db_config(
    request: Request, payload: VectorDBConfigPayload, user: User = Depends(get_current_active_user)
):
    entry = get_provider_entry(payload.type)
    if not entry:
        raise HTTPException(
            status_code=400, detail=f"未知的向量数据库类型: {payload.type}")
    if not entry.get("enabled", True):
        raise HTTPException(status_code=400, detail="该向量数据库类型暂不可用")

    provider_cls = get_provider_class(payload.type)
    if not provider_cls:
        raise HTTPException(
            status_code=400, detail=f"未找到类型 {payload.type} 对应的实现")

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


__all__ = ["router_ai", "router_vector_db"]
