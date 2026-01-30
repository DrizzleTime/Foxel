from typing import List
from fastapi import HTTPException

from models.database import Role, RolePermission, Permission, PathRule, UserRole
from domain.permission.service import PermissionService
from domain.permission.types import PathRuleCreate, PathRuleInfo
from .types import RoleInfo, RoleDetail, RoleCreate, RoleUpdate, SystemRoles


class RoleService:
    """角色管理服务"""

    @classmethod
    async def get_all_roles(cls) -> List[RoleInfo]:
        """获取所有角色"""
        roles = await Role.all().order_by("id")
        return [
            RoleInfo(
                id=r.id,
                name=r.name,
                description=r.description,
                is_system=r.is_system,
                created_at=r.created_at,
            )
            for r in roles
        ]

    @classmethod
    async def get_role(cls, role_id: int) -> RoleDetail:
        """获取角色详情"""
        role = await Role.get_or_none(id=role_id)
        if not role:
            raise HTTPException(404, detail="角色不存在")

        # 获取权限
        role_permissions = await RolePermission.filter(role_id=role_id).prefetch_related(
            "permission"
        )
        permissions = [rp.permission.code for rp in role_permissions]

        # 获取路径规则数量
        path_rules_count = await PathRule.filter(role_id=role_id).count()

        return RoleDetail(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            created_at=role.created_at,
            permissions=permissions,
            path_rules_count=path_rules_count,
        )

    @classmethod
    async def create_role(cls, data: RoleCreate) -> RoleInfo:
        """创建角色"""
        # 检查名称是否已存在
        existing = await Role.get_or_none(name=data.name)
        if existing:
            raise HTTPException(400, detail="角色名称已存在")

        role = await Role.create(
            name=data.name,
            description=data.description,
            is_system=False,
        )

        return RoleInfo(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            created_at=role.created_at,
        )

    @classmethod
    async def update_role(cls, role_id: int, data: RoleUpdate) -> RoleInfo:
        """更新角色"""
        role = await Role.get_or_none(id=role_id)
        if not role:
            raise HTTPException(404, detail="角色不存在")

        if data.name is not None:
            # 检查名称是否与其他角色冲突
            existing = await Role.filter(name=data.name).exclude(id=role_id).first()
            if existing:
                raise HTTPException(400, detail="角色名称已存在")
            role.name = data.name

        if data.description is not None:
            role.description = data.description

        await role.save()

        return RoleInfo(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            created_at=role.created_at,
        )

    @classmethod
    async def delete_role(cls, role_id: int) -> None:
        """删除角色"""
        role = await Role.get_or_none(id=role_id)
        if not role:
            raise HTTPException(404, detail="角色不存在")

        if role.is_system:
            raise HTTPException(400, detail="系统内置角色不可删除")

        # 检查是否有用户使用此角色
        user_count = await UserRole.filter(role_id=role_id).count()
        if user_count > 0:
            raise HTTPException(400, detail=f"有 {user_count} 个用户正在使用此角色，无法删除")

        await role.delete()
        # 清除权限缓存
        PermissionService.clear_cache()

    @classmethod
    async def set_role_permissions(cls, role_id: int, permission_codes: List[str]) -> List[str]:
        """设置角色的权限"""
        role = await Role.get_or_none(id=role_id)
        if not role:
            raise HTTPException(404, detail="角色不存在")

        # 获取权限ID
        permissions = await Permission.filter(code__in=permission_codes)
        permission_map = {p.code: p.id for p in permissions}

        # 验证所有权限代码
        invalid_codes = set(permission_codes) - set(permission_map.keys())
        if invalid_codes:
            raise HTTPException(400, detail=f"无效的权限代码: {', '.join(invalid_codes)}")

        # 删除现有权限
        await RolePermission.filter(role_id=role_id).delete()

        # 添加新权限
        for code in permission_codes:
            await RolePermission.create(
                role_id=role_id,
                permission_id=permission_map[code],
            )

        # 清除权限缓存
        PermissionService.clear_cache()

        return permission_codes

    @classmethod
    async def get_role_path_rules(cls, role_id: int) -> List[PathRuleInfo]:
        """获取角色的路径规则"""
        role = await Role.get_or_none(id=role_id)
        if not role:
            raise HTTPException(404, detail="角色不存在")

        rules = await PathRule.filter(role_id=role_id).order_by("-priority", "id")
        return [
            PathRuleInfo(
                id=r.id,
                role_id=r.role_id,
                path_pattern=r.path_pattern,
                is_regex=r.is_regex,
                can_read=r.can_read,
                can_write=r.can_write,
                can_delete=r.can_delete,
                can_share=r.can_share,
                priority=r.priority,
                created_at=r.created_at,
            )
            for r in rules
        ]

    @classmethod
    async def add_path_rule(cls, role_id: int, data: PathRuleCreate) -> PathRuleInfo:
        """添加路径规则"""
        role = await Role.get_or_none(id=role_id)
        if not role:
            raise HTTPException(404, detail="角色不存在")

        # 验证路径模式
        if data.is_regex:
            import re
            try:
                re.compile(data.path_pattern)
            except re.error as e:
                raise HTTPException(400, detail=f"无效的正则表达式: {e}")

        rule = await PathRule.create(
            role_id=role_id,
            path_pattern=data.path_pattern,
            is_regex=data.is_regex,
            can_read=data.can_read,
            can_write=data.can_write,
            can_delete=data.can_delete,
            can_share=data.can_share,
            priority=data.priority,
        )

        # 清除权限缓存
        PermissionService.clear_cache()

        return PathRuleInfo(
            id=rule.id,
            role_id=rule.role_id,
            path_pattern=rule.path_pattern,
            is_regex=rule.is_regex,
            can_read=rule.can_read,
            can_write=rule.can_write,
            can_delete=rule.can_delete,
            can_share=rule.can_share,
            priority=rule.priority,
            created_at=rule.created_at,
        )

    @classmethod
    async def update_path_rule(cls, rule_id: int, data: PathRuleCreate) -> PathRuleInfo:
        """更新路径规则"""
        rule = await PathRule.get_or_none(id=rule_id)
        if not rule:
            raise HTTPException(404, detail="路径规则不存在")

        # 验证路径模式
        if data.is_regex:
            import re
            try:
                re.compile(data.path_pattern)
            except re.error as e:
                raise HTTPException(400, detail=f"无效的正则表达式: {e}")

        rule.path_pattern = data.path_pattern
        rule.is_regex = data.is_regex
        rule.can_read = data.can_read
        rule.can_write = data.can_write
        rule.can_delete = data.can_delete
        rule.can_share = data.can_share
        rule.priority = data.priority
        await rule.save()

        # 清除权限缓存
        PermissionService.clear_cache()

        return PathRuleInfo(
            id=rule.id,
            role_id=rule.role_id,
            path_pattern=rule.path_pattern,
            is_regex=rule.is_regex,
            can_read=rule.can_read,
            can_write=rule.can_write,
            can_delete=rule.can_delete,
            can_share=rule.can_share,
            priority=rule.priority,
            created_at=rule.created_at,
        )

    @classmethod
    async def delete_path_rule(cls, rule_id: int) -> None:
        """删除路径规则"""
        rule = await PathRule.get_or_none(id=rule_id)
        if not rule:
            raise HTTPException(404, detail="路径规则不存在")

        await rule.delete()
        # 清除权限缓存
        PermissionService.clear_cache()

    @classmethod
    async def ensure_system_roles(cls) -> None:
        """确保系统内置角色存在"""
        system_roles = [
            {
                "name": SystemRoles.ADMIN,
                "description": "管理员角色，拥有所有系统和适配器权限",
                "is_system": True,
            },
            {
                "name": SystemRoles.USER,
                "description": "普通用户角色，需要管理员配置路径权限",
                "is_system": True,
            },
            {
                "name": SystemRoles.VIEWER,
                "description": "只读用户角色，仅可查看文件",
                "is_system": True,
            },
        ]

        for role_data in system_roles:
            existing = await Role.get_or_none(name=role_data["name"])
            if not existing:
                await Role.create(**role_data)

    @classmethod
    async def setup_admin_role_permissions(cls) -> None:
        """为管理员角色设置所有权限"""
        admin_role = await Role.get_or_none(name=SystemRoles.ADMIN)
        if not admin_role:
            return

        # 获取所有权限
        all_permissions = await Permission.all()
        
        # 清除现有权限
        await RolePermission.filter(role_id=admin_role.id).delete()
        
        # 添加所有权限
        for perm in all_permissions:
            await RolePermission.create(role_id=admin_role.id, permission_id=perm.id)

        # 添加全路径访问规则
        existing_rule = await PathRule.filter(
            role_id=admin_role.id, path_pattern="/**"
        ).first()
        if not existing_rule:
            await PathRule.create(
                role_id=admin_role.id,
                path_pattern="/**",
                is_regex=False,
                can_read=True,
                can_write=True,
                can_delete=True,
                can_share=True,
                priority=100,
            )
