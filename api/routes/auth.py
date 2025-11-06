from typing import Annotated
from fastapi import APIRouter, HTTPException, Depends, Form
import hashlib
from fastapi.security import OAuth2PasswordRequestForm
from services.auth import (
    authenticate_user_db,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    register_user,
    Token,
    get_current_active_user,
    User,
    request_password_reset,
    verify_password_reset_token,
    reset_password_with_token,
)
from pydantic import BaseModel
from datetime import timedelta
from api.response import success
from models.database import UserAccount
from services.auth import verify_password, get_password_hash

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
    db_user = await UserAccount.get_or_none(id=current_user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if payload.email is not None:
        exists = await UserAccount.filter(email=payload.email).exclude(id=db_user.id).exists()
        if exists:
            raise HTTPException(status_code=400, detail="邮箱已被占用")
        db_user.email = payload.email

    if payload.full_name is not None:
        db_user.full_name = payload.full_name

    if payload.new_password:
        if not payload.old_password:
            raise HTTPException(status_code=400, detail="请提供原密码")
        if not verify_password(payload.old_password, db_user.hashed_password):
            raise HTTPException(status_code=400, detail="原密码错误")
        db_user.hashed_password = get_password_hash(payload.new_password)

    await db_user.save()

    email = (db_user.email or "").strip().lower()
    md5_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
    gravatar_url = f"https://cn.cravatar.com/avatar/{md5_hash}?s=64&d=identicon"
    return success({
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "full_name": db_user.full_name,
        "gravatar_url": gravatar_url,
    })


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
