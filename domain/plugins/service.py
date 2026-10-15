"""
插件服务模块

负责插件的安装、卸载等管理操作
"""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Union

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from .manager import PluginManager
from .loader import PluginLoader
from .types import (
    PluginInstallResult,
    PluginManifest,
    PluginOut,
)
from models.database import Plugin

logger = logging.getLogger(__name__)


class PluginService:
    """插件服务"""

    _plugins_root = Path("data/plugins")

    # ========== 工具方法 ==========

    @classmethod
    def _get_plugin_dir(cls, plugin_key: str) -> Path:
        """获取插件目录"""
        return cls._plugins_root / plugin_key

    @classmethod
    def _get_bundle_path(cls, rec: Plugin) -> Path:
        """获取前端 bundle 路径"""
        plugin_dir = cls._get_plugin_dir(rec.key)
        # 从 manifest 读取
        if rec.manifest:
            frontend = rec.manifest.get("frontend", {})
            entry = frontend.get("entry")
            if entry:
                return plugin_dir / entry
        # 默认位置
        return plugin_dir / "frontend" / "index.js"

    @classmethod
    async def _get_by_key_or_404(cls, key: str) -> Plugin:
        """通过 key 获取插件，不存在则返回 404"""
        rec = await Plugin.get_or_none(key=key)
        if not rec:
            raise HTTPException(status_code=404, detail="Plugin not found")
        return rec

    @classmethod
    async def _get_by_key_or_id(cls, key_or_id: Union[str, int]) -> Plugin:
        """通过 key 或 ID 获取插件"""
        # 尝试作为 ID
        if isinstance(key_or_id, int) or (isinstance(key_or_id, str) and key_or_id.isdigit()):
            plugin_id = int(key_or_id)
            rec = await Plugin.get_or_none(id=plugin_id)
            if rec:
                return rec
        # 尝试作为 key
        if isinstance(key_or_id, str):
            rec = await Plugin.get_or_none(key=key_or_id)
            if rec:
                return rec
        raise HTTPException(status_code=404, detail="Plugin not found")

    # ========== 安装 ==========

    @classmethod
    async def install_package(cls, file_content: bytes, filename: str, manager: PluginManager) -> PluginInstallResult:
        """
        安装 .foxpkg 插件包

        Args:
            file_content: 插件包内容
            filename: 文件名

        Returns:
            安装结果
        """
        directory = None
        try:
            manifest, directory = PluginLoader.unpack_foxpkg(file_content)
            async with manager.lock(manifest.key):
                return await cls._install_staged(manifest, directory, manager)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("插件安装失败")
            return PluginInstallResult(success=False, message=f"安装失败: {exc}", errors=[str(exc)])
        finally:
            if directory is not None:
                target = cls._get_plugin_dir(manifest.key)
                if not target.is_symlink() or target.resolve() != directory.resolve():
                    shutil.rmtree(directory, ignore_errors=True)

    @classmethod
    async def _install_staged(cls, manifest, directory, manager):
        key = manifest.key
        target = cls._get_plugin_dir(key)
        backup = target.with_name(f".{key}.rollback")
        snapshot = manager.snapshot(key, manifest)
        switched = False
        old_directory = target.resolve() if target.is_symlink() else None
        try:
            prepared = manager.prepare(key, manifest, directory)
            if target.exists() or target.is_symlink():
                target.rename(backup)
            try:
                target.symlink_to(directory.resolve(), target_is_directory=True)
            except BaseException:
                if backup.exists() or backup.is_symlink():
                    backup.rename(target)
                raise
            switched = True
            async with in_transaction() as connection:
                rec = await Plugin.get_or_none(key=key).using_db(connection)
                if rec is None:
                    rec = Plugin(key=key)
                for field in ("name", "version", "description", "author", "website", "github", "license"):
                    setattr(rec, field, getattr(manifest, field))
                rec.manifest = manifest.model_dump(mode="json")
                frontend = manifest.frontend
                rec.open_app = bool(frontend and frontend.open_app)
                for field in ("supported_exts", "default_bounds", "default_maximized", "icon"):
                    setattr(rec, field, getattr(frontend, field) if frontend else None)
                rec.loaded_routes = [router.prefix for router in prepared[0]]
                rec.loaded_processors = [p[0] for p in prepared[1]]
                await rec.save(using_db=connection)
                manager.activate(key, prepared)
        except BaseException:
            manager.restore(key, snapshot)
            if switched:
                target.unlink()
                if backup.exists() or backup.is_symlink():
                    backup.rename(target)
            raise
        for module in snapshot[1].values():
            import sys
            sys.modules.pop(module.__name__, None)
        if backup.is_symlink():
            backup.unlink()
        elif backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if old_directory is not None:
            shutil.rmtree(old_directory, ignore_errors=True)
        return PluginInstallResult(success=True, plugin=PluginOut.model_validate(rec), message="安装成功")

    # ========== 查询 ==========

    @classmethod
    async def list_plugins(cls) -> List[PluginOut]:
        """获取所有插件列表"""
        rows = await Plugin.all().order_by("-id")
        for rec in rows:
            try:
                manifest = PluginLoader.read_manifest(rec.key)
                if manifest:
                    rec.manifest = manifest.model_dump(mode="json")
            except Exception:
                continue
        return [PluginOut.model_validate(r) for r in rows]

    @classmethod
    async def get_plugin(cls, key_or_id: Union[str, int]) -> PluginOut:
        """获取单个插件详情"""
        rec = await cls._get_by_key_or_id(key_or_id)
        try:
            manifest = PluginLoader.read_manifest(rec.key)
            if manifest:
                rec.manifest = manifest.model_dump(mode="json")
        except Exception:
            pass
        return PluginOut.model_validate(rec)

    @classmethod
    async def get_bundle_path(cls, key_or_id: Union[str, int]) -> Path:
        """获取插件前端 bundle 路径"""
        rec = await cls._get_by_key_or_id(key_or_id)
        bundle_path = cls._get_bundle_path(rec)
        if not bundle_path.exists():
            raise HTTPException(status_code=404, detail="Plugin bundle not found")
        return bundle_path

    @classmethod
    async def get_asset_path(cls, key: str, asset_path: str) -> Path:
        """获取插件静态资源路径"""
        rec = await cls._get_by_key_or_404(key)
        plugin_dir = cls._get_plugin_dir(rec.key)

        # 安全检查：防止路径遍历
        asset_path = asset_path.lstrip("/")
        if ".." in asset_path:
            raise HTTPException(status_code=400, detail="Invalid asset path")

        full_path = plugin_dir / asset_path
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Asset not found")

        # 确保路径在插件目录内
        try:
            full_path.resolve().relative_to(plugin_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid asset path")

        return full_path

    # ========== 管理操作 ==========

    @classmethod
    async def delete(cls, key_or_id: Union[str, int], manager: PluginManager) -> None:
        """删除/卸载插件"""
        rec = await cls._get_by_key_or_id(key_or_id)
        async with manager.lock(rec.key):
            rec = await cls._get_by_key_or_id(rec.key)
            target = cls._get_plugin_dir(rec.key)
            tombstone = target.with_name(f".{rec.key}.removed")
            directory = target.resolve() if target.is_symlink() else None
            moved = target.exists() or target.is_symlink()
            if moved:
                target.rename(tombstone)
            try:
                await rec.delete()
            except BaseException:
                if moved:
                    tombstone.rename(target)
                raise
            manager.remove(rec.key)
            manifest = PluginManifest.model_validate(rec.manifest) if rec.manifest else None
            PluginLoader.unload_plugin(rec.key, manifest)
            if tombstone.is_symlink():
                tombstone.unlink()
            elif tombstone.exists():
                shutil.rmtree(tombstone, ignore_errors=True)
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            logger.info("插件 %s 已卸载", rec.key)
