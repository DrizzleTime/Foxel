from pydantic import BaseModel

from models.database import VideoRoom


class VideoRoomCreate(BaseModel):
    name: str
    path: str


class VideoRoomState(BaseModel):
    current_time: float
    paused: bool
    updated_at: str | None = None


class VideoRoomInfo(BaseModel):
    id: int
    token: str
    name: str
    path: str
    created_at: str
    state: VideoRoomState

    @classmethod
    def from_orm(cls, obj: VideoRoom, state: VideoRoomState | None = None):
        return cls(
            id=obj.id,
            token=obj.token,
            name=obj.name,
            path=obj.path,
            created_at=obj.created_at.isoformat(),
            state=state
            or VideoRoomState(
                current_time=obj.current_time,
                paused=obj.paused,
                updated_at=obj.state_updated_at.isoformat() if obj.state_updated_at else None,
            ),
        )
