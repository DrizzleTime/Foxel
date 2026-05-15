from typing import Annotated

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from api.response import success
from domain.auth import User, get_current_active_user
from domain.video_room.service import VideoRoomService
from domain.video_room.types import PlaybackEvent, VideoRoomCreate, VideoRoomInfo

router = APIRouter(prefix="/api/video-rooms", tags=["Video Rooms"])
public_router = APIRouter(prefix="/api/watch", tags=["Video Rooms - Public"])


@router.post("", response_model=VideoRoomInfo)
async def create_video_room(
    request: Request,
    payload: VideoRoomCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    room = await VideoRoomService.create_room(
        user_id=current_user.id,
        path=payload.path,
        name=payload.name,
        expires_in_days=payload.expires_in_days,
        control_mode=payload.control_mode,
    )
    return VideoRoomInfo(
        id=room.id,
        name=room.name,
        token=room.token,
        path=room.path,
        control_mode=room.control_mode,
        created_at=room.created_at.isoformat(),
        expires_at=room.expires_at.isoformat() if room.expires_at else None,
    )


@public_router.get("/{token}")
async def get_watch_room(request: Request, token: str):
    room = await VideoRoomService.get_room_by_token(token)
    state = await VideoRoomService.get_state(room.id)
    return success({"room": VideoRoomInfo(
        id=room.id,
        name=room.name,
        token=room.token,
        path=room.path,
        control_mode=room.control_mode,
        created_at=room.created_at.isoformat(),
        expires_at=room.expires_at.isoformat() if room.expires_at else None,
    ).model_dump(), "playback": state})


@public_router.websocket("/{token}/ws")
async def watch_room_ws(websocket: WebSocket, token: str):
    room = await VideoRoomService.get_room_by_token(token)
    actor = websocket.query_params.get("actor") or "guest"
    await VideoRoomService.ws_connect(room.id, websocket)
    try:
        state = await VideoRoomService.get_state(room.id)
        await websocket.send_json({"type": "snapshot", "playback": state})
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            event_type = msg.get("event")
            if event_type not in {"play", "pause", "seek", "rate"}:
                continue
            position_ms = int(msg.get("position_ms") or 0)
            playback_rate = float(msg.get("playback_rate") or 1.0)
            state = await VideoRoomService.apply_event(
                room=room,
                actor=actor,
                event_type=event_type,
                position_ms=position_ms,
                playback_rate=playback_rate,
            )
            await VideoRoomService.ws_broadcast(room.id, {"type": "playback", "event": event_type, "playback": state, "actor": actor})
    except WebSocketDisconnect:
        pass
    finally:
        await VideoRoomService.ws_disconnect(room.id, websocket)


@public_router.post("/{token}/events")
async def push_watch_event(request: Request, token: str, payload: PlaybackEvent):
    room = await VideoRoomService.get_room_by_token(token)
    actor = request.headers.get("X-Watch-Actor", "guest")
    state = await VideoRoomService.apply_event(
        room=room,
        actor=actor,
        event_type=payload.type,
        position_ms=payload.position_ms,
        playback_rate=payload.playback_rate,
    )
    await VideoRoomService.ws_broadcast(room.id, {"type": "playback", "event": payload.type, "playback": state, "actor": actor})
    return success({"playback": state})
