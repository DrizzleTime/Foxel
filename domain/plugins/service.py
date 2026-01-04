"""
插件服务模块

负责插件的安装、卸载等管理操作
"""

import contextlib
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Union

from fastapi import HTTPException

from domain.plugins.loader import PluginLoadError, PluginLoader
from domain.plugins.types import (
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
    async def install_package(cls, file_content: bytes, filename: str) -> PluginInstallResult:
        """
        安装 .foxpkg 插件包

        Args:
            file_content: 插件包内容
            filename: 文件名

        Returns:
            安装结果
        """
        errors: List[str] = []

        try:
            # 解包
            manifest, plugin_dir = PluginLoader.unpack_foxpkg(file_content)
            plugin_key = manifest.key

            # 检查是否已存在
            existing = await Plugin.get_or_none(key=plugin_key)
            if existing:
                # 更新现有插件
                logger.info(f"更新插件: {plugin_key}")
                rec = existing
            else:
                # 创建新插件
                logger.info(f"安装新插件: {plugin_key}")
                rec = Plugin(key=plugin_key)

            # 更新字段
            rec.name = manifest.name
            rec.version = manifest.version
            rec.description = manifest.description
            rec.author = manifest.author
            rec.website = manifest.website
            rec.github = manifest.github
            rec.license = manifest.license
            rec.manifest = manifest.model_dump(mode="json")

            # 从 manifest.frontend 提取前端配置
            if manifest.frontend:
                rec.open_app = manifest.frontend.open_app or False
                rec.supported_exts = manifest.frontend.supported_exts
                rec.default_bounds = manifest.frontend.default_bounds
                rec.default_maximized = manifest.frontend.default_maximized
                rec.icon = manifest.frontend.icon

            await rec.save()

            # 加载后端组件（如果有）
            loaded_routes: List[str] = []
            loaded_processors: List[str] = []

            if manifest.backend:
                # 加载路由
                if manifest.backend.routes:
                    try:
                        from main import app
                        routers = PluginLoader.load_all_routes(plugin_key, manifest)
                        for router in routers:
                            app.include_router(router)
                            loaded_routes.append(router.prefix)
                    except PluginLoadError as e:
                        errors.append(f"路由加载失败: {e}")
                        logger.error(f"插件 {plugin_key} 路由加载失败: {e}")
                    except Exception as e:
                        errors.append(f"路由加载失败: {e}")
                        logger.exception(f"插件 {plugin_key} 路由加载异常")

                # 加载处理器
                if manifest.backend.processors:
                    try:
                        processor_types = PluginLoader.load_all_processors(plugin_key, manifest)
                        loaded_processors = processor_types
                    except PluginLoadError as e:
                        errors.append(f"处理器加载失败: {e}")
                        logger.error(f"插件 {plugin_key} 处理器加载失败: {e}")
                    except Exception as e:
                        errors.append(f"处理器加载失败: {e}")
                        logger.exception(f"插件 {plugin_key} 处理器加载异常")

            # 更新加载状态
            rec.loaded_routes = loaded_routes if loaded_routes else None
            rec.loaded_processors = loaded_processors if loaded_processors else None
            await rec.save()

            return PluginInstallResult(
                success=True,
                plugin=PluginOut.model_validate(rec),
                message="安装成功" if not errors else "安装完成，但有部分组件加载失败",
                errors=errors if errors else None,
            )

        except PluginLoadError as e:
            logger.error(f"插件安装失败: {e}")
            return PluginInstallResult(
                success=False,
                message=str(e),
                errors=[str(e)],
            )
        except Exception as e:
            logger.exception("插件安装异常")
            return PluginInstallResult(
                success=False,
                message=f"安装失败: {e}",
                errors=[str(e)],
            )

    # ========== 查询 ==========

    @classmethod
    async def list_plugins(cls) -> List[PluginOut]:
        """获取所有插件列表"""
        rows = await Plugin.all().order_by("-id")
        return [PluginOut.model_validate(r) for r in rows]

    @classmethod
    async def get_plugin(cls, key_or_id: Union[str, int]) -> PluginOut:
        """获取单个插件详情"""
        rec = await cls._get_by_key_or_id(key_or_id)
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
    async def delete(cls, key_or_id: Union[str, int]) -> None:
        """删除/卸载插件"""
        rec = await cls._get_by_key_or_id(key_or_id)

        # 获取 manifest 用于卸载组件
        manifest: Optional[PluginManifest] = None
        if rec.manifest:
            try:
                manifest = PluginManifest.model_validate(rec.manifest)
            except Exception:
                pass

        # 卸载后端组件
        if manifest:
            PluginLoader.unload_plugin(rec.key, manifest)

        # 删除数据库记录
        await rec.delete()

        # 删除文件
        with contextlib.suppress(Exception):
            plugin_dir = cls._get_plugin_dir(rec.key)
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)

        logger.info(f"插件 {rec.key} 已卸载")
