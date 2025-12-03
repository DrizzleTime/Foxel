from typing import Annotated, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path

from api.response import success
from application.ai.dependencies import ai_use_cases
from application.ai.use_cases import ABILITIES
from application.auth.dependencies import User, get_current_active_user
from infrastructure.vector_db.service import VectorDBService
from schemas.ai import (
    AIDefaultsUpdate,
    AIModelCreate,
    AIModelUpdate,
    AIProviderCreate,
    AIProviderUpdate,
)


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/providers")
async def list_providers(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    providers = await ai_use_cases.list_providers()
    return success({"providers": providers})


@router.post("/providers")
async def create_provider(
    payload: AIProviderCreate,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    provider = await ai_use_cases.create_provider(payload.model_dump())
    return success(provider)


@router.get("/providers/{provider_id}")
async def get_provider(
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        provider = await ai_use_cases.get_provider(provider_id, with_models=True)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")
    return success(provider)


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: Annotated[int, Path(..., gt=0)],
    payload: AIProviderUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        provider = await ai_use_cases.update_provider(provider_id, data)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")
    return success(provider)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    await ai_use_cases.delete_provider(provider_id)
    return success({"id": provider_id})


@router.post("/providers/{provider_id}/sync-models")
async def sync_models(
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        result = await ai_use_cases.sync_models(provider_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise HTTPException(status_code=502, detail=f"Failed to synchronize models: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return success(result)


@router.get("/providers/{provider_id}/remote-models")
async def fetch_remote_models(
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    try:
        models = await ai_use_cases.fetch_remote_models(provider_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise HTTPException(status_code=502, detail=f"Failed to pull models: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return success({"models": models})


@router.get("/providers/{provider_id}/models")
async def list_models(
    provider_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    models = await ai_use_cases.list_models(provider_id)
    return success({"models": models})


@router.post("/providers/{provider_id}/models")
async def create_model(
    provider_id: Annotated[int, Path(..., gt=0)],
    payload: AIModelCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    model = await ai_use_cases.create_model(provider_id, payload.model_dump())
    return success(model)


@router.put("/models/{model_id}")
async def update_model(
    model_id: Annotated[int, Path(..., gt=0)],
    payload: AIModelUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        model = await ai_use_cases.update_model(model_id, data)
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")
    return success(model)


@router.delete("/models/{model_id}")
async def delete_model(
    model_id: Annotated[int, Path(..., gt=0)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    await ai_use_cases.delete_model(model_id)
    return success({"id": model_id})


def _get_embedding_dimension(entry: Optional[Dict]) -> Optional[int]:
    if not entry:
        return None
    value = entry.get("embedding_dimensions")
    return int(value) if value is not None else None


@router.get("/defaults")
async def get_defaults(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    defaults = await ai_use_cases.get_default_models()
    return success(defaults)


@router.put("/defaults")
async def update_defaults(
    payload: AIDefaultsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    previous = await ai_use_cases.get_default_models()
    try:
        updated = await ai_use_cases.set_default_models(payload.as_mapping())
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
