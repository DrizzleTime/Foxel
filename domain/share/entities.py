from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass(frozen=True)
class ShareLinkEntity:
    id: int
    token: str
    name: str
    paths: List[str]
    access_type: str
    user_id: int
    created_at: datetime
    expires_at: Optional[datetime]
    hashed_password: Optional[str]

    def is_expired(self, current: datetime | None = None) -> bool:
        if not self.expires_at:
            return False
        now = current or datetime.now(timezone.utc)
        return self.expires_at < now

    def requires_password(self) -> bool:
        return self.access_type == "password"
