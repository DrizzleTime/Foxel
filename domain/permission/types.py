from pydantic import BaseModel
from datetime import datetime


# 权限操作类型
class PathAction:
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SHARE = "share"


# 系统权限代码
class SystemPermission:
    USER_CREATE = "system.user.create"
    USER_EDIT = "system.user.edit"
    USER_DELETE = "system.user.delete"
    USER_LIST = "system.user.list"
    ROLE_MANAGE = "system.role.manage"
    CONFIG_EDIT = "system.config.edit"
    AUDIT_VIEW = "system.audit.view"


# 适配器权限代码
class AdapterPermission:
    CREATE = "adapter.create"
    EDIT = "adapter.edit"
    DELETE = "adapter.delete"
    LIST = "adapter.list"


# 所有权限定义
PERMISSION_DEFINITIONS = [
    # 系统权限
    {"code": SystemPermission.USER_CREATE, "name": "创建用户", "category": "system", "description": "允许创建新用户"},
    {"code": SystemPermission.USER_EDIT, "name": "编辑用户", "category": "system", "description": "允许编辑用户信息"},
    {"code": SystemPermission.USER_DELETE, "name": "删除用户", "category": "system", "description": "允许删除用户"},
    {"code": SystemPermission.USER_LIST, "name": "查看用户列表", "category": "system", "description": "允许查看用户列表"},
    {"code": SystemPermission.ROLE_MANAGE, "name": "管理角色和权限", "category": "system", "description": "允许管理角色和权限配置"},
    {"code": SystemPermission.CONFIG_EDIT, "name": "修改系统配置", "category": "system", "description": "允许修改系统配置"},
    {"code": SystemPermission.AUDIT_VIEW, "name": "查看审计日志", "category": "system", "description": "允许查看审计日志"},
    # 适配器权限
    {"code": AdapterPermission.CREATE, "name": "创建存储适配器", "category": "adapter", "description": "允许创建存储适配器"},
    {"code": AdapterPermission.EDIT, "name": "编辑存储适配器", "category": "adapter", "description": "允许编辑存储适配器"},
    {"code": AdapterPermission.DELETE, "name": "删除存储适配器", "category": "adapter", "description": "允许删除存储适配器"},
    {"code": AdapterPermission.LIST, "name": "查看存储适配器列表", "category": "adapter", "description": "允许查看存储适配器列表"},
]


# Pydantic 模型
class PermissionInfo(BaseModel):
    code: str
    name: str
    category: str
    description: str | None = None


class PathRuleInfo(BaseModel):
    id: int
    role_id: int
    path_pattern: str
    is_regex: bool
    can_read: bool
    can_write: bool
    can_delete: bool
    can_share: bool
    priority: int
    created_at: datetime


class PathRuleCreate(BaseModel):
    path_pattern: str
    is_regex: bool = False
    can_read: bool = True
    can_write: bool = False
    can_delete: bool = False
    can_share: bool = False
    priority: int = 0


class PathRuleUpdate(BaseModel):
    path_pattern: str | None = None
    is_regex: bool | None = None
    can_read: bool | None = None
    can_write: bool | None = None
    can_delete: bool | None = None
    can_share: bool | None = None
    priority: int | None = None


class PathPermissionCheck(BaseModel):
    path: str
    action: str


class PathPermissionResult(BaseModel):
    path: str
    action: str
    allowed: bool
    matched_rule: PathRuleInfo | None = None


class UserPermissions(BaseModel):
    user_id: int
    is_admin: bool
    permissions: list[str]  # 系统/适配器权限代码列表
    path_rules: list[PathRuleInfo]  # 路径权限规则
