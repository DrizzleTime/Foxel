import contextlib
import re
import shutil
from pathlib import Path

import aiofiles
import httpx
from fastapi import HTTPException

from domain.plugins.types import PluginCreate, PluginManifestUpdate, PluginOut
from models.database import Plugin


class PluginService:
    _plugins_root = Path("data/plugins")

    @classmethod
    def _folder_name(cls, rec: Plugin) -> str:
        if rec.key:
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", rec.key)
            return safe or str(rec.id)
        return str(rec.id)

    @classmethod
    def _bundle_dir_from_rec(cls, rec: Plugin) -> Path:
        return cls._plugins_root / cls._folder_name(rec) / "current"

    @classmethod
    def _bundle_path_from_rec(cls, rec: Plugin) -> Path:
        return cls._bundle_dir_from_rec(rec) / "index.js"

    @classmethod
    async def _download_bundle(cls, rec: Plugin, url: str) -> None:
        dest_dir = cls._bundle_dir_from_rec(rec)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = cls._bundle_path_from_rec(rec)
        tmp_path = dest_path.with_suffix(".tmp")
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    async with aiofiles.open(tmp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            if not chunk:
                                continue
                            await f.write(chunk)
            tmp_path.replace(dest_path)
        except Exception:
            with contextlib.suppress(Exception):
                if tmp_path.exists():
                    tmp_path.unlink()
            raise

    @classmethod
    async def _ensure_bundle(cls, plugin_id: int) -> Path:
        rec = await cls._get_or_404(plugin_id)
        bundle_path = cls._bundle_path_from_rec(rec)
        if bundle_path.exists():
            return bundle_path

        legacy = cls._plugins_root / str(rec.id) / "current" / "index.js"
        if legacy.exists():
            return legacy

        raise HTTPException(status_code=404, detail="Plugin bundle not found")

    @classmethod
    async def get_bundle_path(cls, plugin_id: int) -> Path:
        return await cls._ensure_bundle(plugin_id)

    @classmethod
    async def create(cls, payload: PluginCreate) -> PluginOut:
        rec = await Plugin.create(**payload.model_dump())
        try:
            await cls._download_bundle(rec, rec.url)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await rec.delete()
            raise HTTPException(status_code=400, detail=f"Failed to fetch plugin: {exc}")
        return PluginOut.model_validate(rec)

    @classmethod
    async def list_plugins(cls) -> list[PluginOut]:
        rows = await Plugin.all().order_by("-id")
        return [PluginOut.model_validate(r) for r in rows]

    @classmethod
    async def _get_or_404(cls, plugin_id: int) -> Plugin:
        rec = await Plugin.get_or_none(id=plugin_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Plugin not found")
        return rec

    @classmethod
    async def delete(cls, plugin_id: int) -> None:
        rec = await cls._get_or_404(plugin_id)
        await rec.delete()
        with contextlib.suppress(Exception):
            dirs = {cls._bundle_dir_from_rec(rec).parent, cls._plugins_root / str(rec.id)}
            for plugin_dir in dirs:
                if plugin_dir.exists():
                    shutil.rmtree(plugin_dir)

    @classmethod
    async def update(cls, plugin_id: int, payload: PluginCreate) -> PluginOut:
        rec = await cls._get_or_404(plugin_id)
        url_changed = rec.url != payload.url
        if url_changed:
            try:
                await cls._download_bundle(rec, payload.url)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to fetch plugin: {exc}")
        rec.url = payload.url
        rec.enabled = payload.enabled
        await rec.save()
        return PluginOut.model_validate(rec)

    @classmethod
    async def update_manifest(
        cls, plugin_id: int, manifest: PluginManifestUpdate
    ) -> PluginOut:
        rec = await cls._get_or_404(plugin_id)
        old_dir = cls._bundle_dir_from_rec(rec).parent
        updates = manifest.model_dump(exclude_none=True)
        if updates:
            for key, value in updates.items():
                setattr(rec, key, value)
            await rec.save()
            new_dir = cls._bundle_dir_from_rec(rec).parent
            if rec.key and new_dir != old_dir:
                candidate_dir = old_dir if old_dir.exists() else (cls._plugins_root / str(rec.id))
                if candidate_dir.exists():
                    new_dir.parent.mkdir(parents=True, exist_ok=True)
                    with contextlib.suppress(Exception):
                        if new_dir.exists():
                            shutil.rmtree(new_dir)
                        shutil.move(str(candidate_dir), str(new_dir))
        return PluginOut.model_validate(rec)
