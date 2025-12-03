from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.response import success
from application.auth.dependencies import User, get_current_active_user
from application.share.dependencies import share_use_cases
from application.share.use_cases import CreateShareInput, ShareUseCases
from application.storage import virtual_fs_service
from domain.share.entities import ShareLinkEntity

public_router = APIRouter(prefix="/api/s", tags=["Share - Public"])
router = APIRouter(prefix="/api/shares", tags=["Share - Management"])


class ShareCreate(BaseModel):
    name: str
    paths: List[str]
    expires_in_days: Optional[int] = 7
    access_type: str = "public"
    password: Optional[str] = None


class ShareInfo(BaseModel):
    id: int
    token: str
    name: str
    paths: List[str]
    created_at: str
    expires_at: Optional[str] = None
    access_type: str

    @classmethod
    def from_entity(cls, entity: ShareLinkEntity):
        return cls(
            id=entity.id,
            token=entity.token,
            name=entity.name,
            paths=entity.paths,
            created_at=entity.created_at.isoformat(),
            expires_at=entity.expires_at.isoformat() if entity.expires_at else None,
            access_type=entity.access_type,
        )


class ShareInfoWithPassword(ShareInfo):
    password: Optional[str] = None


# --- Management Routes ---


@router.post("", response_model=ShareInfoWithPassword)
async def create_share(
    payload: ShareCreate,
    current_user: User = Depends(get_current_active_user),
):
    """
    创建一个新的分享链接。
    """
    share = await share_use_cases.create_share(
        CreateShareInput(
            user_id=current_user.id,
            name=payload.name,
            paths=payload.paths,
            expires_in_days=payload.expires_in_days,
            access_type=payload.access_type,
            password=payload.password,
        )
    )
    share_info_base = ShareInfo.from_entity(share)
    response_data = share_info_base.model_dump()
    if payload.access_type == "password" and payload.password:
        response_data["password"] = payload.password

    return response_data


@router.get("", response_model=List[ShareInfo])
async def get_my_shares(current_user: User = Depends(get_current_active_user)):
    """
    获取当前用户的所有分享链接。
    """
    shares = await share_use_cases.list_user_shares(user_id=current_user.id)
    return [ShareInfo.from_entity(s) for s in shares]


@router.delete("/expired")
async def delete_expired_shares(
    current_user: User = Depends(get_current_active_user),
):
    """
    删除当前用户的所有已过期分享。
    """
    deleted_count = await share_use_cases.delete_expired(user_id=current_user.id)
    return success({"deleted_count": deleted_count})


@router.delete("/{share_id}")
async def delete_share(
    share_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """
    删除一个分享链接。
    """
    await share_use_cases.delete_share(user_id=current_user.id, share_id=share_id)
    return success(msg="分享已取消")


# --- Public Routes ---


class SharePassword(BaseModel):
    password: str


def _ensure_share_password(share: ShareLinkEntity, password: Optional[str]):
    if share.access_type != "password":
        return
    if not password:
        raise HTTPException(status_code=401, detail="需要密码")
    if not ShareUseCases.verify_password(password, share.hashed_password or ""):
        raise HTTPException(status_code=403, detail="密码错误")


@public_router.post("/{token}/verify")
async def verify_password(token: str, payload: SharePassword):
    """
    验证分享链接的密码。
    """
    share = await share_use_cases.get_share_by_token(token)
    if share.access_type != "password":
        raise HTTPException(status_code=400, detail="此分享不需要密码")

    if not ShareUseCases.verify_password(payload.password, share.hashed_password or ""):
        raise HTTPException(status_code=403, detail="密码错误")

    # 在这里可以考虑返回一个有时效性的token用于后续访问，但为了简单起见，
    # 我们让前端在每次请求时都带上密码或一个会话标识。
    # 简单起见，我们只返回成功状态。
    return success(msg="验证成功")


@public_router.get("/{token}/ls")
async def list_share_content(
    token: str, path: str = "/", password: Optional[str] = None
):
    """
    列出分享链接中的文件和目录。
    """
    share = await share_use_cases.get_share_by_token(token)
    _ensure_share_password(share, password)

    content = await share_use_cases.get_shared_item_details(share, path)
    return success(
        {
            "path": path,
            "entries": content.get("items", []),
            "pagination": {
                "total": content.get("total", 0),
                "page": content.get("page", 1),
                "page_size": content.get("page_size", 1),
                "pages": content.get("pages", 1),
            },
        }
    )


@public_router.get("/{token}")
async def get_share_info(token: str):
    """
    获取分享链接的元数据信息。
    """
    share = await share_use_cases.get_share_by_token(token)
    return success(ShareInfo.from_entity(share))


@public_router.get("/{token}/download")
async def download_shared_file(
    token: str, path: str, request: Request, password: Optional[str] = None
):
    """
    下载分享链接中的单个文件。
    """
    if not path or path == "/" or ".." in path.split("/"):
        raise HTTPException(status_code=400, detail="无效的文件路径")

    share = await share_use_cases.get_share_by_token(token)
    _ensure_share_password(share, password)
    base_shared_path = share.paths[0]

    # 判断分享的是文件还是目录
    is_dir = False
    try:
        stat = await virtual_fs_service.stat_file(base_shared_path)
        if stat and stat.get("is_dir"):
            is_dir = True
    except HTTPException as e:
        if "Path is a directory" in str(e.detail) or "Not a file" in str(e.detail):
            is_dir = True
        else:
            # The shared path itself doesn't exist, which is an issue.
            raise HTTPException(status_code=404, detail="分享的源文件不存在")

    if is_dir:
        # 目录分享：拼接路径
        full_virtual_path = f"{base_shared_path.rstrip('/')}/{path.lstrip('/')}"
        if not full_virtual_path.startswith(base_shared_path):
            raise HTTPException(status_code=403, detail="无权访问此路径")
    else:
        # 文件分享：路径应为分享的根路径
        shared_filename = base_shared_path.split("/")[-1]
        request_filename = path.lstrip("/")
        if shared_filename != request_filename:
            raise HTTPException(status_code=403, detail="无权访问此路径")
        full_virtual_path = base_shared_path

    range_header = request.headers.get("Range")
    response = await virtual_fs_service.stream_file(full_virtual_path, range_header)

    # 设置 Content-Disposition 头来强制下载
    filename = full_virtual_path.split("/")[-1]
    response.headers["Content-Disposition"] = (
        f"attachment; filename*=UTF-8''{quote(filename)}"
    )

    return response
