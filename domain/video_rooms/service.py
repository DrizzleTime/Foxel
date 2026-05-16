import secrets
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import Response

from domain.virtual_fs import VirtualFSService
from models.database import UserAccount, VideoRoom
from .types import VideoRoomState


VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".m4v", ".mov", ".mkv", ".avi", ".flv"}


class VideoRoomService:
    @classmethod
    def _is_video_path(cls, path: str) -> bool:
        lower = path.lower()
        return any(lower.endswith(ext) for ext in VIDEO_EXTENSIONS)

    @classmethod
    async def create_room(cls, user: UserAccount, name: str, path: str) -> VideoRoom:
        if not path or path == "/" or ".." in path.split("/"):
            raise HTTPException(status_code=400, detail="无效的视频路径")
        if not cls._is_video_path(path):
            raise HTTPException(status_code=400, detail="仅支持视频文件创建视频房")

        stat = await VirtualFSService.stat_file(path)
        if stat.get("is_dir"):
            raise HTTPException(status_code=400, detail="目录不能创建视频房")

        token = secrets.token_urlsafe(16)
        return await VideoRoom.create(
            token=token,
            name=name or path.rsplit("/", 1)[-1],
            path=path,
            user=user,
            state_updated_at=datetime.now(timezone.utc),
        )

    @classmethod
    async def get_room_by_token(cls, token: str) -> VideoRoom:
        room = await VideoRoom.get_or_none(token=token).prefetch_related("user")
        if not room:
            raise HTTPException(status_code=404, detail="视频房不存在")
        return room

    @classmethod
    def get_effective_state(cls, room: VideoRoom) -> VideoRoomState:
        current_time = float(room.current_time or 0)
        updated_at = room.state_updated_at
        if not room.paused and updated_at:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            current_time += max(0, (datetime.now(timezone.utc) - updated_at).total_seconds())
        return VideoRoomState(
            current_time=max(0, current_time),
            paused=bool(room.paused),
            updated_at=updated_at.isoformat() if updated_at else None,
        )

    @classmethod
    async def update_state(cls, room: VideoRoom, current_time: float, paused: bool) -> VideoRoomState:
        now = datetime.now(timezone.utc)
        room.current_time = max(0, float(current_time or 0))
        room.paused = bool(paused)
        room.state_updated_at = now
        await room.save(update_fields=["current_time", "paused", "state_updated_at"])
        return VideoRoomState(
            current_time=room.current_time,
            paused=room.paused,
            updated_at=now.isoformat(),
        )

    @classmethod
    async def stream_room_file(cls, token: str, range_header: str | None) -> Response:
        room = await cls.get_room_by_token(token)
        response = await VirtualFSService.stream_file(room.path, range_header)
        filename = room.path.rsplit("/", 1)[-1]
        response.headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(filename)}"
        return response
