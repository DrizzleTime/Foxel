from typing import List, Optional
from fastapi import HTTPException

from models.database import (
    UserAccount,
    UserRole,
    RolePermission,
    PathRule,
)
from .matcher import PathMatcher
from .types import (
    PathAction,
    PathRuleInfo,
    PathPermissionResult,
    UserPermissions,
    PermissionInfo,
    PERMISSION_DEFINITIONS,
)


class PermissionService:
    """权限检查服务"""

    # 权限检查结果缓存（简单的内存缓存）
    _cache: dict[str, tuple[bool, float]] = {}
    _cache_ttl = 300  # 5分钟缓存

    @classmethod
    async def check_path_permission(
        cls, user_id: int, path: str, action: str
    ) -> bool:
        """
        检查用户对路径的操作权限
        
        Args:
            user_id: 用户ID
            path: 要检查的路径
            action: 操作类型 (read/write/delete/share)
            
        Returns:
            是否有权限
        """
        import time

        # 检查缓存
        cache_key = f"{user_id}:{path}:{action}"
        if cache_key in cls._cache:
            result, timestamp = cls._cache[cache_key]
            if time.time() - timestamp < cls._cache_ttl:
                return result

        # 获取用户
        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            return False

        # 超级管理员直接放行
        if user.is_admin:
            cls._cache[cache_key] = (True, time.time())
            return True

        # 获取用户所有角色
        user_roles = await UserRole.filter(user_id=user_id).prefetch_related("role")
        role_ids = [ur.role_id for ur in user_roles]

        if not role_ids:
            cls._cache[cache_key] = (False, time.time())
            return False

        # 获取所有角色的路径规则
        path_rules = await PathRule.filter(role_id__in=role_ids).order_by("-priority")

        # 规范化路径
        normalized_path = PathMatcher.normalize_path(path)

        # 按优先级和具体程度匹配
        result = cls._match_path_rules(normalized_path, action, list(path_rules))

        # 如果没有匹配到规则，检查父目录（继承）
        if result is None:
            parent_path = PathMatcher.get_parent_path(normalized_path)
            if parent_path:
                result = await cls.check_path_permission(user_id, parent_path, action)
            else:
                result = False  # 默认拒绝

        cls._cache[cache_key] = (result, time.time())
        return result

    @classmethod
    def _match_path_rules(
        cls, path: str, action: str, rules: List[PathRule]
    ) -> Optional[bool]:
        """
        匹配路径规则
        
        Returns:
            True/False 表示明确的权限结果，None 表示没有匹配到规则
        """
        # 按优先级和具体程度排序
        sorted_rules = sorted(
            rules,
            key=lambda r: (
                r.priority,
                PathMatcher.get_pattern_specificity(r.path_pattern, r.is_regex),
            ),
            reverse=True,
        )

        for rule in sorted_rules:
            if PathMatcher.match_pattern(path, rule.path_pattern, rule.is_regex):
                # 匹配到规则，检查具体操作权限
                if action == PathAction.READ:
                    return rule.can_read
                elif action == PathAction.WRITE:
                    return rule.can_write
                elif action == PathAction.DELETE:
                    return rule.can_delete
                elif action == PathAction.SHARE:
                    return rule.can_share
                else:
                    return False

        return None

    @classmethod
    async def check_system_permission(cls, user_id: int, permission_code: str) -> bool:
        """检查用户的系统/适配器权限"""
        # 获取用户
        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            return False

        # 超级管理员直接放行
        if user.is_admin:
            return True

        # 获取用户所有角色
        user_roles = await UserRole.filter(user_id=user_id)
        role_ids = [ur.role_id for ur in user_roles]

        if not role_ids:
            return False

        role_permission = await RolePermission.filter(
            role_id__in=role_ids, permission_code=permission_code
        ).first()

        return role_permission is not None

    @classmethod
    async def require_path_permission(
        cls, user_id: int, path: str, action: str
    ) -> None:
        """要求用户具有路径权限，否则抛出 403"""
        if not await cls.check_path_permission(user_id, path, action):
            raise HTTPException(403, detail=f"没有权限执行此操作: {action}")

    @classmethod
    async def require_system_permission(
        cls, user_id: int, permission_code: str
    ) -> None:
        """要求用户具有系统权限，否则抛出 403"""
        if not await cls.check_system_permission(user_id, permission_code):
            raise HTTPException(403, detail=f"没有权限: {permission_code}")

    @classmethod
    async def get_user_permissions(cls, user_id: int) -> UserPermissions:
        """获取用户的所有权限"""
        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            raise HTTPException(404, detail="用户不存在")

        # 超级管理员拥有所有权限
        if user.is_admin:
            all_permission_codes = [item["code"] for item in PERMISSION_DEFINITIONS]
            all_path_rules = await PathRule.all()
            return UserPermissions(
                user_id=user_id,
                is_admin=True,
                permissions=all_permission_codes,
                path_rules=[
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
                    for r in all_path_rules
                ],
            )

        # 获取用户角色
        user_roles = await UserRole.filter(user_id=user_id)
        role_ids = [ur.role_id for ur in user_roles]

        # 获取权限
        permissions = []
        if role_ids:
            role_permissions = await RolePermission.filter(role_id__in=role_ids)
            permissions = sorted(set(rp.permission_code for rp in role_permissions))

        # 获取路径规则
        path_rules = []
        if role_ids:
            rules = await PathRule.filter(role_id__in=role_ids)
            path_rules = [
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

        return UserPermissions(
            user_id=user_id,
            is_admin=False,
            permissions=permissions,
            path_rules=path_rules,
        )

    @classmethod
    async def get_all_permissions(cls) -> List[PermissionInfo]:
        """获取所有权限定义"""
        return [
            PermissionInfo(
                code=item["code"],
                name=item["name"],
                category=item["category"],
                description=item.get("description"),
            )
            for item in PERMISSION_DEFINITIONS
        ]

    @classmethod
    async def check_path_permission_detailed(
        cls, user_id: int, path: str, action: str
    ) -> PathPermissionResult:
        """检查路径权限并返回详细结果"""
        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            return PathPermissionResult(path=path, action=action, allowed=False)

        # 超级管理员
        if user.is_admin:
            return PathPermissionResult(path=path, action=action, allowed=True)

        # 获取用户角色
        user_roles = await UserRole.filter(user_id=user_id)
        role_ids = [ur.role_id for ur in user_roles]

        if not role_ids:
            return PathPermissionResult(path=path, action=action, allowed=False)

        # 获取路径规则
        path_rules = await PathRule.filter(role_id__in=role_ids).order_by("-priority")
        normalized_path = PathMatcher.normalize_path(path)

        # 查找匹配的规则
        matched_rule = None
        for rule in sorted(
            path_rules,
            key=lambda r: (
                r.priority,
                PathMatcher.get_pattern_specificity(r.path_pattern, r.is_regex),
            ),
            reverse=True,
        ):
            if PathMatcher.match_pattern(
                normalized_path, rule.path_pattern, rule.is_regex
            ):
                matched_rule = rule
                break

        # 检查权限
        allowed = False
        if matched_rule:
            if action == PathAction.READ:
                allowed = matched_rule.can_read
            elif action == PathAction.WRITE:
                allowed = matched_rule.can_write
            elif action == PathAction.DELETE:
                allowed = matched_rule.can_delete
            elif action == PathAction.SHARE:
                allowed = matched_rule.can_share

        rule_info = None
        if matched_rule:
            rule_info = PathRuleInfo(
                id=matched_rule.id,
                role_id=matched_rule.role_id,
                path_pattern=matched_rule.path_pattern,
                is_regex=matched_rule.is_regex,
                can_read=matched_rule.can_read,
                can_write=matched_rule.can_write,
                can_delete=matched_rule.can_delete,
                can_share=matched_rule.can_share,
                priority=matched_rule.priority,
                created_at=matched_rule.created_at,
            )

        return PathPermissionResult(
            path=path, action=action, allowed=allowed, matched_rule=rule_info
        )

    @classmethod
    def clear_cache(cls, user_id: int | None = None) -> None:
        """清除权限缓存"""
        if user_id is None:
            cls._cache.clear()
        else:
            # 清除特定用户的缓存
            keys_to_delete = [k for k in cls._cache if k.startswith(f"{user_id}:")]
            for k in keys_to_delete:
                del cls._cache[k]

    @classmethod
    async def filter_paths_by_permission(
        cls, user_id: int, paths: List[str], action: str
    ) -> List[str]:
        """过滤出用户有权限的路径列表"""
        result = []
        for path in paths:
            if await cls.check_path_permission(user_id, path, action):
                result.append(path)
        return result
