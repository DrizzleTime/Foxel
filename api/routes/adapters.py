from fastapi import APIRouter, HTTPException, Depends
from tortoise.transactions import in_transaction
from typing import Annotated

from dataclasses import asdict
from typing import Annotated

from api.response import success
from application.storage.adapter_dependencies import adapter_service
from schemas import AdapterCreate, AdapterOut
from application.auth.dependencies import User, get_current_active_user
from application.logging.dependencies import logging_service
router = APIRouter(prefix="/api/adapters", tags=["adapters"])


@router.post("")
async def create_adapter(
    data: AdapterCreate,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        rec = await adapter_service.create_adapter(data.model_dump())
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    await logging_service.action(
        "route:adapters",
        f"Created adapter {rec.name}",
        details=data.model_dump(),
        user_id=current_user.id if hasattr(current_user, "id") else None,
    )
    return success(asdict(rec))


@router.get("")
async def list_adapters(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    adapters = await adapter_service.list_adapters()
    out = [AdapterOut.model_validate(asdict(a)) for a in adapters]
    return success(out)


@router.get("/available")
async def available_adapter_types(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    return success(adapter_service.available_adapter_types())


@router.get("/{adapter_id}")
async def get_adapter(
    adapter_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    rec = await adapter_service.get_adapter(adapter_id)
    if not rec:
        raise HTTPException(404, detail="Not found")
    return success(AdapterOut.model_validate(asdict(rec)))


@router.put("/{adapter_id}")
async def update_adapter(
    adapter_id: int,
    data: AdapterCreate,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        rec = await adapter_service.update_adapter(adapter_id, data.model_dump())
    except ValueError as exc:
        if "Not found" in str(exc):
            raise HTTPException(404, detail="Not found")
        raise HTTPException(400, detail=str(exc))
    await logging_service.action(
        "route:adapters",
        f"Updated adapter {rec.name}",
        details=data.model_dump(),
        user_id=current_user.id if hasattr(current_user, "id") else None,
    )
    return success(asdict(rec))


@router.delete("/{adapter_id}")
async def delete_adapter(
    adapter_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    deleted = await adapter_service.delete_adapter(adapter_id)
    if not deleted:
        raise HTTPException(404, detail="Not found")
    await logging_service.action(
        "route:adapters",
        f"Deleted adapter {adapter_id}",
        details={"adapter_id": adapter_id},
        user_id=current_user.id if hasattr(current_user, "id") else None,
    )
    return success({"deleted": True})
