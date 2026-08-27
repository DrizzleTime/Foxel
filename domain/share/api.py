from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission import require_path_permission
from domain.permission.types import PathAction
from .service import ShareService
from .types import (
    ShareCreate,
    ShareInfo,
    ShareInfoWithPassword,
    SharePassword,
)
from models.database import UserAccount

public_router = APIRouter(prefix="/api/s", tags=["Share - Public"])
router = APIRouter(prefix="/api/shares", tags=["Share - Management"])


@router.post("", response_model=ShareInfoWithPassword)
@audit(
    action=AuditAction.SHARE,
    description="创建分享链接",
    body_fields=["name", "paths", "expires_in_days", "access_type"],
)
@require_path_permission(PathAction.SHARE, "payload.paths")
async def create_share(
    request: Request,
    payload: ShareCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    user_account = await UserAccount.get(id=current_user.id)
    share = await ShareService.create_share_link(
        user=user_account,
        name=payload.name,
        paths=payload.paths,
        expires_in_days=payload.expires_in_days,
        access_type=payload.access_type,
        password=payload.password,
    )
    share_info = ShareInfo.from_orm(share).model_dump()
    if payload.access_type == "password" and payload.password:
        share_info["password"] = payload.password
    return share_info


@router.get("", response_model=List[ShareInfo])
@audit(action=AuditAction.READ, description="获取我的分享列表")
async def get_my_shares(
    request: Request, current_user: Annotated[User, Depends(get_current_active_user)]
):
    user_account = await UserAccount.get(id=current_user.id)
    shares = await ShareService.get_user_shares(user=user_account)
    return [ShareInfo.from_orm(s) for s in shares]


@router.delete("/expired")
@audit(action=AuditAction.DELETE, description="删除已过期分享")
async def delete_expired_shares(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    user_account = await UserAccount.get(id=current_user.id)
    deleted_count = await ShareService.delete_expired_shares(user=user_account)
    return success({"deleted_count": deleted_count})


@router.delete("/{share_id}")
@audit(action=AuditAction.DELETE, description="删除分享链接")
async def delete_share(
    share_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    user_account = await UserAccount.get(id=current_user.id)
    await ShareService.delete_share_link(user=user_account, share_id=share_id)
    return success(msg="分享已取消")


@public_router.post("/{token}/verify")
@audit(
    action=AuditAction.SHARE,
    description="校验分享密码",
    body_fields=["password"],
    redact_fields=["password"],
)
async def verify_password(request: Request, token: str, payload: SharePassword):
    await ShareService.verify_share_password(token, payload.password)
    return success(msg="验证成功")


@public_router.get("/{token}/ls")
@audit(action=AuditAction.SHARE, description="浏览分享内容")
async def list_share_content(
    request: Request,
    token: str,
    path: str = "/",
    password: Optional[str] = None,
    page_num: int = Query(1, alias="page", ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
    cursor: str | None = Query(None, description="游标分页位置"),
):
    share = await ShareService.ensure_share_access(token, password)
    content = await ShareService.get_shared_item_details(
        share=share,
        sub_path=path,
        page_num=page_num,
        page_size=page_size,
        cursor=cursor,
    )
    return success(
        {
            "path": path,
            "entries": content.get("items", []),
            "pagination": content.get("pagination"),
        }
    )


@public_router.get("/{token}")
@audit(action=AuditAction.SHARE, description="获取分享信息")
async def get_share_info(request: Request, token: str):
    share = await ShareService.get_share_by_token(token)
    return success(ShareInfo.from_orm(share))


@public_router.get("/{token}/download")
@audit(action=AuditAction.DOWNLOAD, description="下载分享文件")
async def download_shared_file(
    token: str,
    path: str,
    request: Request,
    password: Optional[str] = None,
):
    return await ShareService.stream_shared_file(token, path, request.headers.get("Range"), password)
