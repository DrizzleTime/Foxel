from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from .service import AgentService
from .types import AgentChatRequest


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat")
@audit(action=AuditAction.CREATE, description="Agent 对话", body_fields=["auto_execute"])
async def chat(
    request: Request,
    payload: AgentChatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await AgentService.chat(payload, current_user)
    return success(data)


@router.post("/chat/stream")
@audit(action=AuditAction.CREATE, description="Agent 对话（SSE）", body_fields=["auto_execute"])
async def chat_stream(
    request: Request,
    payload: AgentChatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return StreamingResponse(
        AgentService.chat_stream(payload, current_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
