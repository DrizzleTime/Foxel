from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends

from application.auth.use_cases import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    AuthService,
    Token,
    TokenData,
    UserPublic as User,
    oauth2_scheme,
)
from domain.auth.entities import UserEntity
from infrastructure.persistence.user_repository import TortoiseUserRepository

auth_service = AuthService(TortoiseUserRepository())


async def request_password_reset(email: str) -> bool:
    return await auth_service.request_password_reset(email)


async def verify_password_reset_token(token: str) -> UserEntity:
    user = await auth_service.verify_password_reset_token(token)
    return user


async def reset_password_with_token(token: str, new_password: str) -> None:
    await auth_service.reset_password_with_token(token, new_password)


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    return await auth_service.get_current_user(token)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return await auth_service.get_current_active_user(current_user)


async def register_user(username: str, password: str, email: str = None, full_name: str = None):
    return await auth_service.register_user(username, password, email, full_name)


async def has_users() -> bool:
    return await auth_service.has_users()


async def create_access_token(data: dict, expires_delta: timedelta | None = None):
    return await auth_service.create_access_token(data, expires_delta)


async def authenticate_user_db(username_or_email: str, password: str):
    entity = await auth_service.authenticate_user(username_or_email, password)
    if not entity:
        return None
    return User(
        id=entity.id,
        username=entity.username,
        email=entity.email,
        full_name=entity.full_name,
        disabled=entity.disabled,
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return auth_service.verify_password(plain_password, hashed_password)  # type: ignore[attr-defined]


def get_password_hash(password: str) -> str:
    return auth_service.get_password_hash(password)  # type: ignore[attr-defined]


__all__ = [
    "auth_service",
    "User",
    "Token",
    "TokenData",
    "oauth2_scheme",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "get_current_user",
    "get_current_active_user",
    "authenticate_user_db",
    "register_user",
    "has_users",
    "create_access_token",
    "verify_password",
    "get_password_hash",
    "request_password_reset",
    "verify_password_reset_token",
    "reset_password_with_token",
]
