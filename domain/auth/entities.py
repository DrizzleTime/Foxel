from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UserEntity:
    id: int
    username: str
    email: Optional[str]
    full_name: Optional[str]
    hashed_password: str
    disabled: bool


__all__ = ["UserEntity"]
