from __future__ import annotations

from application.share.use_cases import ShareUseCases
from domain.share.repositories import ShareLinkRepository
from infrastructure.persistence.share_repository import TortoiseShareLinkRepository

_repository: ShareLinkRepository = TortoiseShareLinkRepository()
share_use_cases = ShareUseCases(repository=_repository)

__all__ = ["share_use_cases"]
