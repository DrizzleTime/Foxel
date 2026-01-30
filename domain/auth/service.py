import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError

from domain.config import ConfigService
from models.database import UserAccount
from .types import (
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    Token,
    TokenData,
    UpdateMeRequest,
    User,
    UserInDB,
)

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


class AuthService:
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
    algorithm = ALGORITHM
    access_token_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
    password_reset_token_expire_minutes = PASSWORD_RESET_TOKEN_EXPIRE_MINUTES

    @staticmethod
    def _to_bytes(value: str) -> bytes:
        return value.encode("utf-8")

    @classmethod
    async def get_secret_key(cls) -> str:
        return await ConfigService.get_secret_key("SECRET_KEY", None)

    @classmethod
    def _normalize_email(cls, email: str | None) -> str:
        return (email or "").strip().lower()

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(cls._to_bytes(plain_password), hashed_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    @classmethod
    def get_password_hash(cls, password: str) -> str:
        encoded = cls._to_bytes(password)
        if len(encoded) > 72:
            raise HTTPException(status_code=400, detail="密码过长")
        return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")

    @classmethod
    async def get_user_db(cls, username_or_email: str) -> UserInDB | None:
        user = await UserAccount.get_or_none(username=username_or_email)
        if not user:
            user = await UserAccount.get_or_none(email=username_or_email)
        if user:
            return UserInDB(
                id=user.id,
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                disabled=user.disabled,
                is_admin=user.is_admin,
                hashed_password=user.hashed_password,
            )
        return None

    @classmethod
    async def authenticate_user_db(cls, username_or_email: str, password: str) -> UserInDB | None:
        user = await cls.get_user_db(username_or_email)
        if not user:
            return None
        if not cls.verify_password(password, user.hashed_password):
            return None
        return user

    @classmethod
    async def has_users(cls) -> bool:
        user_count = await UserAccount.all().count()
        return user_count > 0

    @classmethod
    async def register_user(cls, payload: RegisterRequest):
        if await cls.has_users():
            raise HTTPException(status_code=403, detail="系统已初始化，不允许注册新用户")
        exists = await UserAccount.get_or_none(username=payload.username)
        if exists:
            raise HTTPException(status_code=400, detail="用户名已存在")
        hashed = cls.get_password_hash(payload.password)
        # 第一个用户自动成为超级管理员
        user = await UserAccount.create(
            username=payload.username,
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hashed,
            disabled=False,
            is_admin=True,  # 第一个用户是超级管理员
        )
        return user

    @classmethod
    async def create_access_token(cls, data: dict, expires_delta: timedelta | None = None):
        to_encode = data.copy()
        if "sub" not in to_encode and "username" in to_encode:
            to_encode["sub"] = to_encode["username"]
        expire = _now() + (expires_delta or timedelta(minutes=15))
        to_encode.update({"exp": expire})
        secret_key = await cls.get_secret_key()
        encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=cls.algorithm)
        return encoded_jwt

    @classmethod
    async def login(cls, form: OAuth2PasswordRequestForm) -> Token:
        user = await cls.authenticate_user_db(form.username, form.password)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 更新最后登录时间
        db_user = await UserAccount.get_or_none(id=user.id)
        if db_user:
            db_user.last_login = _now()
            await db_user.save(update_fields=["last_login"])
        
        access_token_expires = timedelta(minutes=cls.access_token_expire_minutes)
        access_token = await cls.create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        return Token(access_token=access_token, token_type="bearer")

    @classmethod
    def _build_profile(cls, user: User | UserInDB | UserAccount) -> dict:
        email = cls._normalize_email(getattr(user, "email", None))
        md5_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
        gravatar_url = f"https://cn.cravatar.com/avatar/{md5_hash}?s=64&d=identicon"
        return {
            "id": user.id,
            "username": user.username,
            "email": getattr(user, "email", None),
            "full_name": getattr(user, "full_name", None),
            "gravatar_url": gravatar_url,
            "is_admin": getattr(user, "is_admin", False),
        }

    @classmethod
    def get_profile(cls, user: User | UserInDB | UserAccount) -> dict:
        return cls._build_profile(user)

    @classmethod
    async def update_me(cls, payload: UpdateMeRequest, current_user: User) -> dict:
        db_user = await UserAccount.get_or_none(id=current_user.id)
        if not db_user:
            raise HTTPException(status_code=404, detail="用户不存在")

        if payload.email is not None:
            exists = (
                await UserAccount.filter(email=payload.email)
                .exclude(id=db_user.id)
                .exists()
            )
            if exists:
                raise HTTPException(status_code=400, detail="邮箱已被占用")
            db_user.email = payload.email

        if payload.full_name is not None:
            db_user.full_name = payload.full_name

        if payload.new_password:
            if not payload.old_password:
                raise HTTPException(status_code=400, detail="请提供原密码")
            if not cls.verify_password(payload.old_password, db_user.hashed_password):
                raise HTTPException(status_code=400, detail="原密码错误")
            db_user.hashed_password = cls.get_password_hash(payload.new_password)

        await db_user.save()
        return cls._build_profile(db_user)

    @classmethod
    async def request_password_reset(cls, payload: PasswordResetRequest) -> bool:
        normalized = cls._normalize_email(payload.email)
        if not normalized:
            return False
        user = await UserAccount.get_or_none(email=normalized)
        if not user or not user.email:
            return False

        token = await PasswordResetStore.create(user)
        try:
            await cls._send_password_reset_email(user, token)
        except Exception as exc:  # noqa: BLE001
            await PasswordResetStore.mark_used(token)
            await PasswordResetStore.invalidate_user(user.id)
            raise HTTPException(status_code=500, detail="邮件发送失败") from exc
        return True

    @classmethod
    async def verify_password_reset_token(cls, token: str) -> UserAccount:
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

    @classmethod
    async def reset_password_with_token(cls, payload: PasswordResetConfirm) -> None:
        record = await PasswordResetStore.get(payload.token)
        if not record:
            raise HTTPException(status_code=400, detail="重置链接无效")
        if record.expires_at < _now():
            await PasswordResetStore.mark_used(payload.token)
            raise HTTPException(status_code=400, detail="重置链接已过期")

        user = await UserAccount.get_or_none(id=record.user_id)
        if not user:
            raise HTTPException(status_code=400, detail="重置链接无效")
        user.hashed_password = cls.get_password_hash(payload.password)
        await user.save(update_fields=["hashed_password"])
        await PasswordResetStore.mark_used(payload.token)
        await PasswordResetStore.invalidate_user(user.id)

    @classmethod
    async def get_current_user(cls, token: str):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            secret_key = await cls.get_secret_key()
            payload = jwt.decode(token, secret_key, algorithms=[cls.algorithm])
            username = payload.get("sub")
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except InvalidTokenError:
            raise credentials_exception
        user = await cls.get_user_db(token_data.username)
        if user is None:
            raise credentials_exception
        return user

    @classmethod
    async def get_current_active_user(cls, current_user: User):
        if current_user.disabled:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user

    @classmethod
    async def _send_password_reset_email(cls, user: UserAccount, token: str) -> None:
        from domain.email import EmailService

        app_domain = await ConfigService.get("APP_DOMAIN", None)
        base_url = (app_domain or "http://localhost:5173").rstrip("/")
        reset_link = f"{base_url}/reset-password?token={token}"
        await EmailService.enqueue_email(
            recipients=[user.email],
            subject="Foxel 密码重置",
            template="password_reset",
            context={
                "username": user.username,
                "reset_link": reset_link,
                "expire_minutes": cls.password_reset_token_expire_minutes,
            },
        )


async def _current_user_dep(token: Annotated[str, Depends(AuthService.oauth2_scheme)]):
    return await AuthService.get_current_user(token)


async def _current_active_user_dep(
    current_user: Annotated[User, Depends(_current_user_dep)],
):
    return await AuthService.get_current_active_user(current_user)


# 方便依赖注入与外部使用
get_current_user = _current_user_dep
get_current_active_user = _current_active_user_dep
authenticate_user_db = AuthService.authenticate_user_db
create_access_token = AuthService.create_access_token
register_user = AuthService.register_user
request_password_reset = AuthService.request_password_reset
verify_password_reset_token = AuthService.verify_password_reset_token
reset_password_with_token = AuthService.reset_password_with_token
has_users = AuthService.has_users
verify_password = AuthService.verify_password
get_password_hash = AuthService.get_password_hash
