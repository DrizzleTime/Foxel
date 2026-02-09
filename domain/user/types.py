from datetime import datetime

from pydantic import BaseModel


class UserInfo(BaseModel):
    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool
    is_admin: bool
    created_at: datetime
    last_login: datetime | None = None


class UserDetail(UserInfo):
    roles: list[str]
    created_by_username: str | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    email: str | None = None
    full_name: str | None = None
    is_admin: bool = False
    disabled: bool = False
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    password: str | None = None
    is_admin: bool | None = None
    disabled: bool | None = None


class UserRoleAssign(BaseModel):
    role_ids: list[int]

