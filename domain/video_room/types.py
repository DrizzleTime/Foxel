from typing import Literal, Optional

from pydantic import BaseModel, Field


VideoEventType = Literal["play", "pause", "seek", "rate"]


class VideoRoomCreate(BaseModel):
    path: str
    name: Optional[str] = None
    expires_in_days: Optional[int] = 1
    control_mode: Literal["host_only", "everyone"] = "everyone"


class VideoRoomJoin(BaseModel):
    nickname: Optional[str] = None


class VideoRoomInfo(BaseModel):
    id: int
    name: str
    token: str
    path: str
    control_mode: str
    created_at: str
    expires_at: Optional[str] = None


class PlaybackState(BaseModel):
    position_ms: int = 0
    is_paused: bool = True
    playback_rate: float = Field(default=1.0, ge=0.25, le=4.0)
    updated_at: str
    updated_by: str


class RoomStateResponse(BaseModel):
    room: VideoRoomInfo
    playback: PlaybackState
    members_online: int


class PlaybackEvent(BaseModel):
    type: VideoEventType
    position_ms: int = 0
    playback_rate: float = Field(default=1.0, ge=0.25, le=4.0)
    client_ts: Optional[int] = None
