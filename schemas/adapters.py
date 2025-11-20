import re
from typing import Dict, Optional
from pydantic import BaseModel, Field, field_validator


class AdapterBase(BaseModel):
    name: str
    type: str = Field(pattern=r"^[a-z0-9_]+$")
    config: Dict = Field(default_factory=dict)
    enabled: bool = True
    path: str = None
    sub_path: Optional[str] = None

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v: str):
        if not isinstance(v, str):
            raise ValueError("type required")
        normalized = v.strip().lower()
        if not normalized:
            raise ValueError("type required")
        if not re.fullmatch(r"[a-z0-9_]+", normalized):
            raise ValueError("type must be lowercase alphanumeric or underscore")
        return normalized


class AdapterCreate(AdapterBase):
    @staticmethod
    def normalize_mount_path(p: str) -> str:
        p = p.strip()
        if not p.startswith('/'):
            p = '/' + p
        p = p.rstrip('/')
        return p or '/'

    @field_validator("path")
    def _v_mount(cls, v: str):
        if not v:
            raise ValueError("mount_path required")
        return cls.normalize_mount_path(v)


class AdapterOut(AdapterBase):
    id: int
    path: str = None
    sub_path: Optional[str] = None

    class Config:
        from_attributes = True
