"""Activate exactly the version selected by the database."""
import json
import logging
import uuid
from pathlib import Path

from .loader import PluginLoadError, PluginLoader
from .types import PluginManifest

logger = logging.getLogger(__name__)


async def activate_record(plugin, manager):
    from .service import PluginService

    snapshot = manager.snapshot(plugin.key, None)
    try:
        plugin.status = "loading"
        await plugin.save(update_fields=["status"])
        if not plugin.manifest or not plugin.version:
            raise PluginLoadError("没有可激活的已安装版本，请重新安装")
        manifest = PluginManifest.model_validate(plugin.manifest)
        directory = PluginService.active_directory(plugin)
        disk = PluginManifest.model_validate(json.loads((directory / "manifest.json").read_text()))
        if manifest != disk or manifest.key != plugin.key or manifest.version != plugin.version:
            raise PluginLoadError("数据库与磁盘 manifest 不一致，请重新安装")
        # Adopt legacy mutable directories once; subsequent versions have permanent paths.
        alias = PluginLoader.get_plugin_dir(plugin.key)
        if not plugin.active_directory and not alias.is_symlink():
            directory = alias.with_name(f".version-{plugin.key}-{uuid.uuid4().hex}")
            alias.rename(directory)
            alias.symlink_to(directory.resolve(), target_is_directory=True)
        plugin.active_directory = directory.name
        # Recover the convenience link after an interrupted switch. DB remains authoritative.
        if alias.is_symlink() and alias.resolve() != directory.resolve():
            alias.unlink()
        if not alias.exists():
            alias.symlink_to(directory.resolve(), target_is_directory=True)
        prepared = manager.prepare(plugin.key, manifest, directory)
        plugin.loaded_routes = [r.prefix for r in prepared[0]]
        plugin.loaded_processors = [p[0] for p in prepared[1]]
        plugin.status = "active"
        plugin.last_error = None
        await plugin.save()
        manager.activate(plugin.key, prepared)
    except Exception as exc:
        manager.restore(plugin.key, snapshot)
        plugin.status = "active" if snapshot[0] is not None else "failed"
        plugin.last_error = str(exc)
        if plugin.status == "failed":
            plugin.loaded_routes = []
            plugin.loaded_processors = []
        await plugin.save()
        raise


async def load_installed_plugins(app) -> tuple[int, list[str]]:
    from models.database import Plugin

    errors = []
    count = 0
    manager = app.state.plugin_manager
    for plugin in await Plugin.all():
        if plugin.status == "disabled":
            continue
        async with manager.lock(plugin.key):
            try:
                await activate_record(plugin, manager)
                count += 1
            except Exception as exc:
                message = f"插件 {plugin.key} 加载失败: {exc}"
                logger.exception(message)
                errors.append(message)
    return count, errors


async def init_plugins(app):
    count, errors = await load_installed_plugins(app)
    logger.info("插件加载完成：%d 成功，%d 失败", count, len(errors))
