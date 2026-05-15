import asyncio
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, WebSocket
from starlette.websockets import WebSocketState

from models.database import VideoRoom


VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}


class VideoRoomService:
    _runtime_states: dict[int, dict] = {}
    _room_clients: dict[int, set[WebSocket]] = {}
    _lock = asyncio.Lock()

    @classmethod
    def _now(cls) -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _iso_now(cls) -> str:
        return cls._now().isoformat()

    @classmethod
    def _ensure_video_path(cls, path: str) -> None:
        p = path.lower()
        if not any(p.endswith(ext) for ext in VIDEO_EXTS):
            raise HTTPException(status_code=400, detail="仅支持视频文件创建视频间")

    @classmethod
    def _calc_expires_at(cls, expires_in_days: Optional[int]) -> Optional[datetime]:
        if expires_in_days is None or expires_in_days <= 0:
            return None
        return cls._now() + timedelta(days=expires_in_days)

    @classmethod
    async def create_room(cls, *, user_id: int, path: str, name: Optional[str], expires_in_days: Optional[int], control_mode: str):
        cls._ensure_video_path(path)
        token = secrets.token_urlsafe(18)
        room_name = name or f"{path.split('/')[-1]} 的视频间"
        room = await VideoRoom.create(
            token=token,
            name=room_name,
            path=path,
            owner_id=user_id,
            control_mode=control_mode,
            expires_at=cls._calc_expires_at(expires_in_days),
        )
        cls._runtime_states[room.id] = {
            "position_ms": 0,
            "is_paused": True,
            "playback_rate": 1.0,
            "updated_at": cls._iso_now(),
            "updated_by": f"user:{user_id}",
        }
        return room

    @classmethod
    async def get_room_by_token(cls, token: str) -> VideoRoom:
        room = await VideoRoom.get_or_none(token=token)
        if not room:
            raise HTTPException(status_code=404, detail="视频间不存在")
        if room.expires_at and room.expires_at < cls._now():
            raise HTTPException(status_code=410, detail="视频间已过期")
        return room

    @classmethod
    async def get_state(cls, room_id: int) -> dict:
        return cls._runtime_states.setdefault(
            room_id,
            {
                "position_ms": 0,
                "is_paused": True,
                "playback_rate": 1.0,
                "updated_at": cls._iso_now(),
                "updated_by": "system",
            },
        )

    @classmethod
    async def apply_event(cls, *, room: VideoRoom, actor: str, event_type: str, position_ms: int, playback_rate: float):
        state = await cls.get_state(room.id)
        if room.control_mode == "host_only" and actor != f"user:{room.owner_id}":
            raise HTTPException(status_code=403, detail="仅房主可控制播放")

        if event_type == "play":
            state["is_paused"] = False
        elif event_type == "pause":
            state["is_paused"] = True
        elif event_type == "seek":
            state["position_ms"] = max(position_ms, 0)
        elif event_type == "rate":
            state["playback_rate"] = playback_rate
        state["updated_at"] = cls._iso_now()
        state["updated_by"] = actor
        return state

    @classmethod
    async def ws_connect(cls, room_id: int, websocket: WebSocket):
        await websocket.accept()
        async with cls._lock:
            clients = cls._room_clients.setdefault(room_id, set())
            clients.add(websocket)

    @classmethod
    async def ws_disconnect(cls, room_id: int, websocket: WebSocket):
        async with cls._lock:
            clients = cls._room_clients.get(room_id)
            if not clients:
                return
            clients.discard(websocket)
            if not clients:
                cls._room_clients.pop(room_id, None)

    @classmethod
    async def ws_broadcast(cls, room_id: int, payload: dict):
        clients = list(cls._room_clients.get(room_id, set()))
        if not clients:
            return
        text = json.dumps(payload)
        stale: list[WebSocket] = []
        for ws in clients:
            try:
                if ws.application_state == WebSocketState.CONNECTED:
                    await ws.send_text(text)
                else:
                    stale.append(ws)
            except Exception:
                stale.append(ws)

        if stale:
            async with cls._lock:
                pool = cls._room_clients.get(room_id, set())
                for ws in stale:
                    pool.discard(ws)
                if not pool:
                    cls._room_clients.pop(room_id, None)
