from __future__ import annotations

from typing import Dict, Optional

from domain.auth.entities import UserEntity
from domain.auth.repositories import UserRepository
from models.database import UserAccount


def _to_entity(record: UserAccount) -> UserEntity:
    return UserEntity(
        id=record.id,
        username=record.username,
        email=record.email,
        full_name=record.full_name,
        hashed_password=record.hashed_password,
        disabled=record.disabled,
    )


class TortoiseUserRepository(UserRepository):
    async def get_by_username(self, username: str) -> UserEntity | None:
        rec = await UserAccount.get_or_none(username=username)
        return _to_entity(rec) if rec else None

    async def get_by_email(self, email: str) -> UserEntity | None:
        rec = await UserAccount.get_or_none(email=email)
        return _to_entity(rec) if rec else None

    async def get_by_username_or_email(self, value: str) -> UserEntity | None:
        rec = await UserAccount.get_or_none(username=value)
        if not rec:
            rec = await UserAccount.get_or_none(email=value)
        return _to_entity(rec) if rec else None

    async def get_by_id(self, user_id: int) -> UserEntity | None:
        rec = await UserAccount.get_or_none(id=user_id)
        return _to_entity(rec) if rec else None

    async def create_user(self, data: Dict) -> UserEntity:
        rec = await UserAccount.create(**data)
        return _to_entity(rec)

    async def update_user(self, user_id: int, updates: Dict) -> UserEntity | None:
        rec = await UserAccount.get_or_none(id=user_id)
        if not rec:
            return None
        for k, v in updates.items():
            setattr(rec, k, v)
        await rec.save()
        return _to_entity(rec)

    async def count_users(self) -> int:
        return await UserAccount.all().count()


__all__ = ["TortoiseUserRepository"]
