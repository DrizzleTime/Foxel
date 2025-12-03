from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from pydantic import BaseModel

from application.config.dependencies import config_service
from application.logging.dependencies import logging_service
from domain.auth.entities import UserEntity
from domain.auth.repositories import UserRepository

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 365
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 10

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def _now() -> datetime:
    return datetime.now(timezone.utc)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class UserPublic(BaseModel):
    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


@dataclass
class PasswordResetEntry:
    user_id: int
    email: str
    username: str
    expires_at: datetime
    used: bool = False


class PasswordResetStore:
    _tokens: dict[str, PasswordResetEntry] = {}
    _lock = asyncio.Lock()

    @classmethod
    def _cleanup(cls):
        now = _now()
        for token, record in list(cls._tokens.items()):
            if record.used or record.expires_at < now:
                cls._tokens.pop(token, None)

    @classmethod
    async def create(cls, user: UserEntity) -> str:
        async with cls._lock:
            cls._cleanup()
            for key, record in list(cls._tokens.items()):
                if record.user_id == user.id:
                    cls._tokens.pop(key, None)
            token = secrets.token_urlsafe(32)
            expires_at = _now() + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
            cls._tokens[token] = PasswordResetEntry(
                user_id=user.id,
                email=user.email or "",
                username=user.username,
                expires_at=expires_at,
            )
            return token

    @classmethod
    async def get(cls, token: str) -> PasswordResetEntry | None:
        async with cls._lock:
            cls._cleanup()
            record = cls._tokens.get(token)
            if not record or record.used:
                return None
            return record

    @classmethod
    async def mark_used(cls, token: str) -> None:
        async with cls._lock:
            record = cls._tokens.get(token)
            if record:
                record.used = True
            cls._cleanup()

    @classmethod
    async def invalidate_user(cls, user_id: int, except_token: str | None = None) -> None:
        async with cls._lock:
            for key, record in list(cls._tokens.items()):
                if record.user_id == user_id and key != except_token:
                    cls._tokens.pop(key, None)
            cls._cleanup()


class AuthService:
    def __init__(self, repository: UserRepository):
        self._repo = repository

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    async def has_users(self) -> bool:
        return (await self._repo.count_users()) > 0

    async def register_user(
        self, username: str, password: str, email: str | None = None, full_name: str | None = None
    ) -> UserEntity:
        if await self.has_users():
            raise HTTPException(status_code=403, detail="系统已初始化，不允许注册新用户")
        existing = await self._repo.get_by_username(username)
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")
        hashed = self.get_password_hash(password)
        return await self._repo.create_user(
            {
                "username": username,
                "email": email,
                "full_name": full_name,
                "hashed_password": hashed,
                "disabled": False,
            }
        )

    async def authenticate_user(self, username_or_email: str, password: str) -> UserEntity | None:
        user = await self._repo.get_by_username_or_email(username_or_email)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user

    async def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        to_encode = data.copy()
        if "sub" not in to_encode and "username" in to_encode:
            to_encode["sub"] = to_encode["username"]
        expire = _now() + (expires_delta or timedelta(minutes=15))
        to_encode.update({"exp": expire})
        secret_key = await config_service.get_secret_key("SECRET_KEY", None)
        encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
        return encoded_jwt

    async def get_user_db(self, username_or_email: str) -> UserEntity | None:
        return await self._repo.get_by_username_or_email(username_or_email)

    async def get_current_user(self, token: Annotated[str, Depends(oauth2_scheme)]):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            secret_key = await config_service.get_secret_key("SECRET_KEY", None)
            payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except InvalidTokenError:
            raise credentials_exception
        user = await self.get_user_db(token_data.username or "")
        if user is None:
            raise credentials_exception
        return UserPublic.model_validate(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "disabled": user.disabled,
            }
        )

    async def get_current_active_user(self, current_user: UserPublic):
        if current_user.disabled:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user

    async def update_profile(
        self,
        user_id: int,
        email: str | None = None,
        full_name: str | None = None,
        old_password: str | None = None,
        new_password: str | None = None,
    ) -> UserEntity:
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        updates: Dict[str, Any] = {}
        if email is not None:
            existing_email = await self._repo.get_by_email(email)
            if existing_email and existing_email.id != user_id:
                raise HTTPException(status_code=400, detail="邮箱已被占用")
            updates["email"] = email
        if full_name is not None:
            updates["full_name"] = full_name
        if new_password:
            if not old_password or not self.verify_password(old_password, user.hashed_password):
                raise HTTPException(status_code=400, detail="原密码错误")
            updates["hashed_password"] = self.get_password_hash(new_password)
        if not updates:
            return user
        updated = await self._repo.update_user(user_id, updates)
        if not updated:
            raise HTTPException(status_code=404, detail="用户不存在")
        return updated

    async def request_password_reset(self, email: str) -> bool:
        normalized = (email or "").strip().lower()
        if not normalized:
            return False
        user = await self._repo.get_by_email(normalized)
        if not user or not user.email:
            return False

        token = await PasswordResetStore.create(user)
        try:
            await self._send_password_reset_email(user, token)
        except Exception as exc:  # noqa: BLE001
            await PasswordResetStore.mark_used(token)
            await PasswordResetStore.invalidate_user(user.id)
            await logging_service.error(
                "auth",
                f"Failed to enqueue password reset email: {exc}",
                details={"user_id": user.id},
                user_id=user.id,
            )
            raise HTTPException(status_code=500, detail="邮件发送失败") from exc
        await logging_service.action(
            "auth",
            "Password reset requested",
            details={"user_id": user.id},
            user_id=user.id,
        )
        return True

    async def verify_password_reset_token(self, token: str) -> UserEntity:
        record = await PasswordResetStore.get(token)
        if not record:
            raise HTTPException(status_code=400, detail="重置链接无效")
        user = await self._repo.get_by_id(record.user_id)
        if not user:
            raise HTTPException(status_code=400, detail="重置链接无效")
        if record.expires_at < _now():
            await PasswordResetStore.mark_used(token)
            raise HTTPException(status_code=400, detail="重置链接已过期")
        return user

    async def reset_password_with_token(self, token: str, new_password: str) -> None:
        record = await PasswordResetStore.get(token)
        if not record:
            raise HTTPException(status_code=400, detail="重置链接无效")
        if record.expires_at < _now():
            await PasswordResetStore.mark_used(token)
            raise HTTPException(status_code=400, detail="重置链接已过期")

        user = await self._repo.get_by_id(record.user_id)
        if not user:
            raise HTTPException(status_code=400, detail="重置链接无效")
        await self._repo.update_user(user.id, {"hashed_password": self.get_password_hash(new_password)})
        await PasswordResetStore.mark_used(token)
        await PasswordResetStore.invalidate_user(user.id)
        await logging_service.action(
            "auth",
            "Password reset via email",
            details={"user_id": user.id},
            user_id=user.id,
        )

    @staticmethod
    async def _send_password_reset_email(user: UserEntity, token: str) -> None:
        from application.email.service import EmailService

        app_domain = await config_service.get("APP_DOMAIN", None)
        base_url = (app_domain or "http://localhost:5173").rstrip("/")
        reset_link = f"{base_url}/reset-password?token={token}"
        await EmailService.enqueue_email(
            recipients=[user.email],
            subject="Foxel 密码重置",
            template="password_reset",
            context={
                "username": user.username,
                "reset_link": reset_link,
                "expire_minutes": PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            },
        )


__all__ = [
    "AuthService",
    "Token",
    "TokenData",
    "UserPublic",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "oauth2_scheme",
]
