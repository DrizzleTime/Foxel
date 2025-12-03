from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from domain.share.entities import ShareLinkEntity
from domain.share.repositories import ShareLinkRepository
from models.database import ShareLink


def _to_entity(model: ShareLink) -> ShareLinkEntity:
    return ShareLinkEntity(
        id=model.id,
        token=model.token,
        name=model.name,
        paths=list(model.paths or []),
        access_type=model.access_type,
        user_id=model.user_id,
        created_at=model.created_at,
        expires_at=model.expires_at,
        hashed_password=model.hashed_password,
    )


class TortoiseShareLinkRepository(ShareLinkRepository):
    async def create(self, share: ShareLinkEntity) -> ShareLinkEntity:
        model = await ShareLink.create(
            token=share.token,
            name=share.name,
            paths=share.paths,
            user_id=share.user_id,
            expires_at=share.expires_at,
            access_type=share.access_type,
            hashed_password=share.hashed_password,
            created_at=share.created_at,
        )
        return _to_entity(model)

    async def delete(self, share_id: int, user_id: int) -> bool:
        deleted_count = await ShareLink.filter(id=share_id, user_id=user_id).delete()
        return deleted_count > 0

    async def delete_expired(self, user_id: int) -> int:
        now = datetime.now(timezone.utc)
        deleted_count = await ShareLink.filter(
            user_id=user_id, expires_at__lte=now
        ).delete()
        return deleted_count

    async def get_by_token(self, token: str) -> ShareLinkEntity | None:
        share = await ShareLink.get_or_none(token=token).prefetch_related("user")
        return _to_entity(share) if share else None

    async def list_by_user(self, user_id: int) -> List[ShareLinkEntity]:
        shares = await ShareLink.filter(user_id=user_id).order_by("-created_at")
        return [_to_entity(share) for share in shares]


__all__ = ["TortoiseShareLinkRepository"]
