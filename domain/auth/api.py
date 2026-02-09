from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from api.response import success
from domain.audit import AuditAction, audit
from .service import AuthService, get_current_active_user
from .types import (
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    Token,
    UpdateMeRequest,
    User,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", summary="注册用户（首个用户为管理员）")
@audit(
    action=AuditAction.REGISTER,
    description="注册用户",
    body_fields=["username", "email", "full_name"],
    redact_fields=["password"],
)
async def register(request: Request, data: RegisterRequest):
    user = await AuthService.register_user(data)
    return success({"username": user.username}, msg="注册成功")


@router.post("/login")
@audit(action=AuditAction.LOGIN, description="用户登录", body_fields=["username"], redact_fields=["password"])
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    return await AuthService.login(form_data)


@router.get("/me", summary="获取当前登录用户信息")
@audit(action=AuditAction.READ, description="获取当前用户信息")
async def get_me(
    request: Request, current_user: Annotated[User, Depends(get_current_active_user)]
):
    profile = AuthService.get_profile(current_user)
    return success(profile)


@router.put("/me", summary="更新当前登录用户信息")
@audit(
    action=AuditAction.UPDATE,
    description="更新当前用户信息",
    body_fields=["email", "full_name"],
    redact_fields=["old_password", "new_password"],
)
async def update_me(
    request: Request,
    payload: UpdateMeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    profile = await AuthService.update_me(payload, current_user)
    return success(profile)


@router.post("/password-reset/request", summary="请求密码重置邮件")
@audit(action=AuditAction.RESET_PASSWORD, description="请求密码重置邮件", body_fields=["email"])
async def password_reset_request_endpoint(request: Request, payload: PasswordResetRequest):
    await AuthService.request_password_reset(payload)
    return success(msg="如果邮箱存在，将发送重置邮件")


@router.get("/password-reset/verify", summary="校验密码重置令牌")
@audit(action=AuditAction.RESET_PASSWORD, description="校验密码重置令牌", redact_fields=["token"])
async def password_reset_verify(request: Request, token: str):
    user = await AuthService.verify_password_reset_token(token)
    return success({"username": user.username, "email": user.email})


@router.post("/password-reset/confirm", summary="使用令牌重置密码")
@audit(
    action=AuditAction.RESET_PASSWORD,
    description="重置密码",
    body_fields=["token"],
    redact_fields=["token", "password"],
)
async def password_reset_confirm(request: Request, payload: PasswordResetConfirm):
    await AuthService.reset_password_with_token(payload)
    return success(msg="密码已重置")
