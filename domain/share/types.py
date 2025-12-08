from typing import List, Optional

from pydantic import BaseModel

from models.database import ShareLink


class ShareCreate(BaseModel):
    name: str
    paths: List[str]
    expires_in_days: Optional[int] = 7
    access_type: str = "public"
    password: Optional[str] = None


class SharePassword(BaseModel):
    password: str


class ShareInfo(BaseModel):
    id: int
    token: str
    name: str
    paths: List[str]
    created_at: str
    expires_at: Optional[str] = None
    access_type: str

    @classmethod
    def from_orm(cls, obj: ShareLink):
        return cls(
            id=obj.id,
            token=obj.token,
            name=obj.name,
            paths=obj.paths,
            created_at=obj.created_at.isoformat(),
            expires_at=obj.expires_at.isoformat() if obj.expires_at else None,
            access_type=obj.access_type,
        )


class ShareInfoWithPassword(ShareInfo):
    password: Optional[str] = None
