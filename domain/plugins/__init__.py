"""
Foxel 插件系统

提供 .foxpkg 插件包的安装、管理和运行时加载功能。
"""

from .loader import PluginLoadError, PluginLoader
from .service import PluginService
from .startup import init_plugins, load_installed_plugins

__all__ = [
    "PluginLoader",
    "PluginLoadError",
    "PluginService",
    "init_plugins",
    "load_installed_plugins",
]
