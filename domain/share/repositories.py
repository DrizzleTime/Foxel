from __future__ import annotations

from typing import List, Protocol

from .entities import ShareLinkEntity


class ShareLinkRepository(Protocol):
    async def create(self, share: ShareLinkEntity) -> ShareLinkEntity: ...

    async def delete(self, share_id: int, user_id: int) -> bool: ...

    async def delete_expired(self, user_id: int) -> int: ...

    async def get_by_token(self, token: str) -> ShareLinkEntity | None: ...

    async def list_by_user(self, user_id: int) -> List[ShareLinkEntity]: ...


__all__ = ["ShareLinkRepository"]
