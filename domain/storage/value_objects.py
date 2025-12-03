from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualPath:
    mount_path: str
    relative_path: str

    def absolute(self) -> str:
        mount = self.mount_path.rstrip("/") or "/"
        rel = self.relative_path.lstrip("/")
        if not rel:
            return mount
        if mount == "/":
            return f"/{rel}"
        return f"{mount}/{rel}"


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"
