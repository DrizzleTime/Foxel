from dataclasses import dataclass
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

@dataclass(slots=True)
class PermissionContext:
    exists: bool
    is_admin: bool
    path_rules: List[PathRule]


class PermissionService:
    """权限检查服务"""

    # 权限检查结果缓存（简单的内存缓存）
    _cache: dict[str, tuple[bool, float]] = {}
    _context_cache: dict[int, tuple[PermissionContext, float]] = {}
    _cache_ttl = 300  # 5分钟缓存

    @classmethod
    def _now(cls) -> float:
        import time

        return time.time()

    @classmethod
    def _is_cache_valid(cls, timestamp: float) -> bool:
        return cls._now() - timestamp < cls._cache_ttl

    @classmethod
    def _get_cached_result(cls, cache_key: str) -> Optional[bool]:
        cached = cls._cache.get(cache_key)
        if not cached:
            return None
        result, timestamp = cached
        if cls._is_cache_valid(timestamp):
            return result
        cls._cache.pop(cache_key, None)
        return None

    @classmethod
    def _sort_path_rules(cls, rules: List[PathRule]) -> List[PathRule]:
        return sorted(
            rules,
            key=lambda r: (
                r.priority,
                PathMatcher.get_pattern_specificity(r.path_pattern, r.is_regex),
            ),
            reverse=True,
        )

    @classmethod
    def _match_sorted_path_rules(
        cls, path: str, action: str, sorted_rules: List[PathRule]
    ) -> Optional[bool]:
        for rule in sorted_rules:
            if PathMatcher.match_pattern(path, rule.path_pattern, rule.is_regex):
                if action == PathAction.READ:
                    return rule.can_read
                if action == PathAction.WRITE:
                    return rule.can_write
                if action == PathAction.DELETE:
                    return rule.can_delete
                if action == PathAction.SHARE:
                    return rule.can_share
                return False
        return None

    @classmethod
    async def _get_permission_context(cls, user_id: int) -> PermissionContext:
        cached = cls._context_cache.get(user_id)
        if cached:
            context, timestamp = cached
            if cls._is_cache_valid(timestamp):
                return context
            cls._context_cache.pop(user_id, None)

        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            context = PermissionContext(exists=False, is_admin=False, path_rules=[])
            cls._context_cache[user_id] = (context, cls._now())
            return context

        if user.is_admin:
            context = PermissionContext(exists=True, is_admin=True, path_rules=[])
            cls._context_cache[user_id] = (context, cls._now())
            return context

        user_roles = await UserRole.filter(user_id=user_id)
        role_ids = [ur.role_id for ur in user_roles]
        if not role_ids:
            context = PermissionContext(exists=True, is_admin=False, path_rules=[])
            cls._context_cache[user_id] = (context, cls._now())
            return context

        path_rules = await PathRule.filter(role_id__in=role_ids)
        context = PermissionContext(
            exists=True,
            is_admin=False,
            path_rules=cls._sort_path_rules(list(path_rules)),
        )
        cls._context_cache[user_id] = (context, cls._now())
        return context

    @classmethod
    def _check_path_permission_with_context(
        cls,
        user_id: int,
        normalized_path: str,
        action: str,
        context: PermissionContext,
    ) -> bool:
        if not context.exists:
            return False
        if context.is_admin:
            return True

        checked_cache_keys: List[str] = []
        current_path = normalized_path

        while True:
            cache_key = f"{user_id}:{current_path}:{action}"
            cached_result = cls._get_cached_result(cache_key)
            if cached_result is not None:
                result = cached_result
                break

            checked_cache_keys.append(cache_key)
            result = cls._match_sorted_path_rules(current_path, action, context.path_rules)
            if result is not None:
                break

            parent_path = PathMatcher.get_parent_path(current_path)
            if not parent_path:
                result = False
                break
            current_path = parent_path

        timestamp = cls._now()
        for cache_key in checked_cache_keys:
            cls._cache[cache_key] = (result, timestamp)
        return result

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
        normalized_path = PathMatcher.normalize_path(path)
        cache_key = f"{user_id}:{normalized_path}:{action}"
        cached_result = cls._get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result

        context = await cls._get_permission_context(user_id)
        result = cls._check_path_permission_with_context(user_id, normalized_path, action, context)
        cls._cache[cache_key] = (result, cls._now())
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
        return cls._match_sorted_path_rules(path, action, cls._sort_path_rules(rules))

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
        context = await cls._get_permission_context(user_id)
        if not context.exists:
            return PathPermissionResult(path=path, action=action, allowed=False)

        if context.is_admin:
            return PathPermissionResult(path=path, action=action, allowed=True)

        if not context.path_rules:
            return PathPermissionResult(path=path, action=action, allowed=False)

        normalized_path = PathMatcher.normalize_path(path)

        matched_rule = None
        for rule in context.path_rules:
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
            cls._context_cache.clear()
        else:
            keys_to_delete = [k for k in cls._cache if k.startswith(f"{user_id}:")]
            for k in keys_to_delete:
                del cls._cache[k]
            cls._context_cache.pop(user_id, None)

    @classmethod
    async def filter_paths_by_permission(
        cls, user_id: int, paths: List[str], action: str
    ) -> List[str]:
        """过滤出用户有权限的路径列表"""
        if not paths:
            return []

        context = await cls._get_permission_context(user_id)
        if not context.exists:
            return []
        if context.is_admin:
            return list(paths)

        result = []
        for path in paths:
            normalized_path = PathMatcher.normalize_path(path)
            if cls._check_path_permission_with_context(user_id, normalized_path, action, context):
                result.append(path)
        return result
