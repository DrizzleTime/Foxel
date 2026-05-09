from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.response import success
from domain.auth import User, get_current_active_user

from .service import NoticeService

router = APIRouter(prefix="/api/notices", tags=["notices"])


@router.get("")
async def list_notices(
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = Query(1, ge=1),
):
    data = await NoticeService.list_notices(page=page)
    return data.model_dump()


@router.get("/popup")
async def get_popup_notice(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    item = await NoticeService.get_popup_notice()
    return success(item.model_dump() if item else None)


@router.post("/{notice_id}/dismiss")
async def dismiss_popup_notice(
    notice_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    await NoticeService.dismiss_popup(notice_id)
    return success()
