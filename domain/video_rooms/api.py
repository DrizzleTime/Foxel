from typing import Annotated

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission import require_path_permission
from domain.permission.types import PathAction
from models.database import UserAccount
from .service import VideoRoomService
from .types import VideoRoomCreate, VideoRoomInfo
from .ws import video_room_ws_manager

router = APIRouter(prefix="/api/video-rooms", tags=["Video Rooms"])


@router.post("", response_model=VideoRoomInfo)
@audit(action=AuditAction.SHARE, description="创建视频房", body_fields=["name", "path"])
@require_path_permission(PathAction.SHARE, "payload.path")
async def create_video_room(
    request: Request,
    payload: VideoRoomCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    user_account = await UserAccount.get(id=current_user.id)
    room = await VideoRoomService.create_room(
        user=user_account,
        name=payload.name,
        path=payload.path,
    )
    return VideoRoomInfo.from_orm(room, VideoRoomService.get_effective_state(room))


@router.get("/{token}", response_model=VideoRoomInfo)
@audit(action=AuditAction.SHARE, description="获取视频房信息")
async def get_video_room(request: Request, token: str):
    room = await VideoRoomService.get_room_by_token(token)
    return VideoRoomInfo.from_orm(room, VideoRoomService.get_effective_state(room))


@router.get("/{token}/stream")
@audit(action=AuditAction.DOWNLOAD, description="播放视频房文件")
async def stream_video_room(token: str, request: Request):
    return await VideoRoomService.stream_room_file(token, request.headers.get("Range"))


@router.websocket("/{token}/ws")
async def video_room_ws(websocket: WebSocket, token: str):
    room = await VideoRoomService.get_room_by_token(token)
    await video_room_ws_manager.connect(token, websocket)
    try:
        state = VideoRoomService.get_effective_state(room)
        await websocket.send_json({"type": "state", "state": state.model_dump()})
        while True:
            data = await websocket.receive_json()
            if data.get("type") != "state":
                continue
            state = await VideoRoomService.update_state(
                room,
                current_time=float(data.get("current_time") or 0),
                paused=bool(data.get("paused")),
            )
            await video_room_ws_manager.broadcast(
                token,
                {"type": "state", "state": state.model_dump()},
                exclude=websocket,
            )
    except WebSocketDisconnect:
        pass
    finally:
        video_room_ws_manager.disconnect(token, websocket)
