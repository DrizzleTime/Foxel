from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StorageMount:
    """领域层挂载描述，隔离 ORM 细节。"""

    id: int
    name: str
    type: str
    config: dict[str, Any]
    enabled: bool
    path: str
    sub_path: str | None = None

    def normalized_path(self) -> str:
        path = self.path or "/"
        return path if path.startswith("/") else f"/{path}"

    def contains(self, absolute_path: str) -> bool:
        norm_mount = self.normalized_path().rstrip("/")
        norm_path = absolute_path if absolute_path.startswith("/") else f"/{absolute_path}"
        if norm_mount:
            return norm_path == norm_mount or norm_path.startswith(f"{norm_mount}/")
        return True

    def relative_path(self, absolute_path: str) -> str:
        norm_mount = self.normalized_path()
        norm_path = absolute_path if absolute_path.startswith("/") else f"/{absolute_path}"
        rel = norm_path[len(norm_mount):].lstrip("/")
        return rel
