import hashlib
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from api.response import success
from application.auth.dependencies import (
    auth_service,
    authenticate_user_db,
    create_access_token,
    get_current_active_user,
    get_password_hash,
    register_user,
    request_password_reset,
    reset_password_with_token,
    verify_password,
    verify_password_reset_token,
)
from application.auth.use_cases import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    UserPublic as User,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    full_name: str | None = None


@router.post("/register", summary="注册第一个管理员用户")
async def register(data: RegisterRequest):
    """
    仅当系统中没有用户时，才允许注册。
    """
    user = await register_user(
        username=data.username,
        password=data.password,
        email=data.email,
        full_name=data.full_name,
    )
    return success({"username": user.username}, msg="初始用户注册成功")


@router.post("/login")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = await authenticate_user_db(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = await create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", summary="获取当前登录用户信息")
async def get_me(current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    返回当前登录用户的基本信息，并附带 gravatar 头像链接。
    """
    email = (current_user.email or "").strip().lower()
    md5_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
    gravatar_url = f"https://cn.cravatar.com/avatar/{md5_hash}?s=64&d=identicon"
    return success({
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "gravatar_url": gravatar_url,
    })


class UpdateMeRequest(BaseModel):
    email: str | None = None
    full_name: str | None = None
    old_password: str | None = None
    new_password: str | None = None


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    password: str


@router.put("/me", summary="更新当前登录用户信息")
async def update_me(
    payload: UpdateMeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    updated = await auth_service.update_profile(
        user_id=current_user.id,
        email=payload.email,
        full_name=payload.full_name,
        old_password=payload.old_password,
        new_password=payload.new_password,
    )

    email = (updated.email or "").strip().lower()
    md5_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
    gravatar_url = f"https://cn.cravatar.com/avatar/{md5_hash}?s=64&d=identicon"
    return success(
        {
            "id": updated.id,
            "username": updated.username,
            "email": updated.email,
            "full_name": updated.full_name,
            "gravatar_url": gravatar_url,
        }
    )


@router.post("/password-reset/request", summary="请求密码重置邮件")
async def password_reset_request_endpoint(payload: PasswordResetRequest):
    await request_password_reset(payload.email)
    return success(msg="如果邮箱存在，将发送重置邮件")


@router.get("/password-reset/verify", summary="校验密码重置令牌")
async def password_reset_verify(token: str):
    user = await verify_password_reset_token(token)
    return success({
        "username": user.username,
        "email": user.email,
    })


@router.post("/password-reset/confirm", summary="使用令牌重置密码")
async def password_reset_confirm(payload: PasswordResetConfirm):
    await reset_password_with_token(payload.token, payload.password)
    return success(msg="密码已重置")
