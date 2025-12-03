from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .entities import ShareLinkEntity


@dataclass(frozen=True)
class ShareAccessDecision:
    allowed: bool
    reason: str | None = None


class ShareAccessService:
    def is_path_allowed(
        self, share: ShareLinkEntity, target_path: str
    ) -> ShareAccessDecision:
        if not share.paths:
            return ShareAccessDecision(False, "Share has no paths")
        base_path = share.paths[0].rstrip("/")
        target_norm = target_path.rstrip("/")
        if target_norm == base_path or target_norm.startswith(f"{base_path}/"):
            return ShareAccessDecision(True)
        return ShareAccessDecision(False, "Path not allowed")


__all__ = ["ShareAccessService", "ShareAccessDecision"]
