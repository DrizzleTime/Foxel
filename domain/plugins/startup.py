"""
插件启动加载模块

负责在应用启动时加载所有已安装的插件
"""

import logging
from typing import TYPE_CHECKING, List, Tuple

from .loader import PluginLoadError, PluginLoader
from .types import PluginManifest

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def load_installed_plugins(app: "FastAPI") -> Tuple[int, List[str]]:
    """
    加载所有已安装的插件

    Args:
        app: FastAPI 应用实例

    Returns:
        (成功加载数量, 错误列表)
    """
    from models.database import Plugin

    errors: List[str] = []
    loaded_count = 0

    try:
        plugins = await Plugin.all()
    except Exception as e:
        logger.error(f"查询插件列表失败: {e}")
        return 0, [f"查询插件列表失败: {e}"]

    for plugin in plugins:
        if not plugin.key:
            continue

        try:
            # 获取 manifest
            manifest = None
            if plugin.manifest:
                try:
                    manifest = PluginManifest.model_validate(plugin.manifest)
                except Exception:
                    # 尝试从文件系统读取
                    manifest = PluginLoader.read_manifest(plugin.key)
            else:
                manifest = PluginLoader.read_manifest(plugin.key)

            if not manifest:
                logger.warning(f"插件 {plugin.key} 缺少 manifest，跳过加载")
                continue

            # 加载后端路由
            loaded_routes: List[str] = []
            if manifest.backend and manifest.backend.routes:
                try:
                    routers = PluginLoader.load_all_routes(plugin.key, manifest)
                    for router in routers:
                        app.include_router(router)
                        loaded_routes.append(router.prefix)
                    logger.info(f"插件 {plugin.key} 加载了 {len(routers)} 个路由")
                except PluginLoadError as e:
                    errors.append(f"插件 {plugin.key} 路由加载失败: {e}")
                    logger.error(f"插件 {plugin.key} 路由加载失败: {e}")

            # 加载处理器
            loaded_processors: List[str] = []
            if manifest.backend and manifest.backend.processors:
                try:
                    processor_types = PluginLoader.load_all_processors(plugin.key, manifest)
                    loaded_processors = processor_types
                    logger.info(f"插件 {plugin.key} 注册了 {len(processor_types)} 个处理器")
                except PluginLoadError as e:
                    errors.append(f"插件 {plugin.key} 处理器加载失败: {e}")
                    logger.error(f"插件 {plugin.key} 处理器加载失败: {e}")

            # 更新数据库记录
            plugin.loaded_routes = loaded_routes if loaded_routes else None
            plugin.loaded_processors = loaded_processors if loaded_processors else None
            await plugin.save()

            loaded_count += 1
            logger.info(f"插件 {plugin.key} 加载完成")

        except Exception as e:
            error_msg = f"插件 {plugin.key} 加载异常: {e}"
            errors.append(error_msg)
            logger.exception(error_msg)

    return loaded_count, errors


async def init_plugins(app: "FastAPI") -> None:
    """
    初始化插件系统

    在应用启动时调用
    """
    logger.info("开始加载已安装插件...")

    loaded_count, errors = await load_installed_plugins(app)

    if errors:
        logger.warning(f"插件加载完成，共 {loaded_count} 个成功，{len(errors)} 个错误")
        for error in errors:
            logger.warning(f"  - {error}")
    else:
        logger.info(f"插件加载完成，共 {loaded_count} 个插件")
