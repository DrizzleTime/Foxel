from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException


class VirtualFSCommonMixin:
    CROSS_TRANSFER_TEMP_ROOT = Path("data/tmp/cross_transfer")
    DIRECT_REDIRECT_CONFIG_KEY = "enable_direct_download_307"

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _build_absolute_path(mount_path: str, rel_path: str) -> str:
        rel_norm = rel_path.lstrip("/")
        mount_norm = mount_path.rstrip("/")
        if not mount_norm:
            return "/" + rel_norm if rel_norm else "/"
        return f"{mount_norm}/{rel_norm}" if rel_norm else mount_norm

    @staticmethod
    def _join_rel(base: str, name: str) -> str:
        if not base:
            return name.lstrip("/")
        if not name:
            return base
        return f"{base.rstrip('/')}/{name.lstrip('/')}"

    @staticmethod
    def _parent_rel(rel: str) -> str:
        if not rel or "/" not in rel:
            return ""
        return rel.rsplit("/", 1)[0]

    @staticmethod
    async def _ensure_method(adapter: Any, method: str):
        func = getattr(adapter, method, None)
        if not callable(func):
            raise HTTPException(501, detail=f"Adapter does not implement {method}")
        return func
