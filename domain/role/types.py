from pydantic import BaseModel
from datetime import datetime


class RoleInfo(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_system: bool
    created_at: datetime


class RoleDetail(RoleInfo):
    permissions: list[str]  # 权限代码列表
    path_rules_count: int


class RoleCreate(BaseModel):
    name: str
    description: str | None = None


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str]


# 预置角色名称
class SystemRoles:
    ADMIN = "Admin"
    USER = "User"
    VIEWER = "Viewer"
