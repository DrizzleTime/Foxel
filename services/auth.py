import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated
import secrets

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from pydantic import BaseModel

from models.database import UserAccount
from services.config import ConfigCenter
from services.logging import LogService

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 365
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    async def create(cls, user: UserAccount) -> str:
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


async def get_secret_key():
    return await ConfigCenter.get_secret_key(
        "SECRET_KEY", None
    )


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    id:int
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    hashed_password: str


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


async def get_user_db(username_or_email: str):
    user = await UserAccount.get_or_none(username=username_or_email)
    if not user:
        user = await UserAccount.get_or_none(email=username_or_email)
    if user:
        return UserInDB(
            id= user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            disabled=user.disabled,
            hashed_password=user.hashed_password,
        )


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def authenticate_user_db(username_or_email: str, password: str):
    user = await get_user_db(username_or_email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def register_user(username: str, password: str, email: str = None, full_name: str = None):
    if await has_users():
        raise HTTPException(status_code=403, detail="系统已初始化，不允许注册新用户")
    exists = await UserAccount.get_or_none(username=username)
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    hashed = get_password_hash(password)
    user = await UserAccount.create(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hashed,
        disabled=False,
    )
    return user


async def has_users() -> bool:
    """
    检查数据库中是否存在任何用户
    """
    user_count = await UserAccount.all().count()
    return user_count > 0


async def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if "sub" not in to_encode and "username" in to_encode:
        to_encode["sub"] = to_encode["username"]
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    secret_key = await get_secret_key()
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


async def _send_password_reset_email(user: UserAccount, token: str) -> None:
    from services.email import EmailService

    app_domain = await ConfigCenter.get("APP_DOMAIN", None)
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


async def request_password_reset(email: str) -> bool:
    normalized = _normalize_email(email)
    if not normalized:
        return False
    user = await UserAccount.get_or_none(email=normalized)
    if not user or not user.email:
        return False

    token = await PasswordResetStore.create(user)
    try:
        await _send_password_reset_email(user, token)
    except Exception as exc:  # noqa: BLE001
        await PasswordResetStore.mark_used(token)
        await PasswordResetStore.invalidate_user(user.id)
        await LogService.error(
            "auth",
            f"Failed to enqueue password reset email: {exc}",
            details={"user_id": user.id},
            user_id=user.id,
        )
        raise HTTPException(status_code=500, detail="邮件发送失败") from exc
    await LogService.action(
        "auth",
        "Password reset requested",
        details={"user_id": user.id},
        user_id=user.id,
    )
    return True


async def verify_password_reset_token(token: str) -> UserAccount:
    record = await PasswordResetStore.get(token)
    if not record:
        raise HTTPException(status_code=400, detail="重置链接无效")
    user = await UserAccount.get_or_none(id=record.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="重置链接无效")
    if record.expires_at < _now():
        await PasswordResetStore.mark_used(token)
        raise HTTPException(status_code=400, detail="重置链接已过期")
    return user


async def reset_password_with_token(token: str, new_password: str) -> None:
    record = await PasswordResetStore.get(token)
    if not record:
        raise HTTPException(status_code=400, detail="重置链接无效")
    if record.expires_at < _now():
        await PasswordResetStore.mark_used(token)
        raise HTTPException(status_code=400, detail="重置链接已过期")

    user = await UserAccount.get_or_none(id=record.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="重置链接无效")
    user.hashed_password = get_password_hash(new_password)
    await user.save(update_fields=["hashed_password"])
    await PasswordResetStore.mark_used(token)
    await PasswordResetStore.invalidate_user(user.id)
    await LogService.action(
        "auth",
        "Password reset via email",
        details={"user_id": user.id},
        user_id=user.id,
    )


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        secret_key = await get_secret_key()
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = await get_user_db(token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
