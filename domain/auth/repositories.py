from __future__ import annotations

from typing import Dict, Optional, Protocol

from domain.auth.entities import UserEntity


class UserRepository(Protocol):
    async def get_by_username(self, username: str) -> UserEntity | None: ...

    async def get_by_email(self, email: str) -> UserEntity | None: ...

    async def get_by_username_or_email(self, value: str) -> UserEntity | None: ...

    async def get_by_id(self, user_id: int) -> UserEntity | None: ...

    async def create_user(self, data: Dict) -> UserEntity: ...

    async def update_user(self, user_id: int, updates: Dict) -> UserEntity | None: ...

    async def count_users(self) -> int: ...


__all__ = ["UserRepository"]
