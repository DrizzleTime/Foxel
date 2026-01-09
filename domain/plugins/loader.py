"""
插件加载器模块

负责：
1. .foxpkg 解包和验证
2. 插件文件部署
3. 后端路由动态加载
4. 处理器动态注册
"""

import io
import json
import shutil
import sys
import zipfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter

from .types import (
    ManifestProcessorConfig,
    ManifestRouteConfig,
    PluginManifest,
)


class PluginLoadError(Exception):
    """插件加载错误"""

    pass


class PluginLoader:
    """插件加载器"""

    PLUGINS_ROOT = Path("data/plugins")

    # 已加载的插件模块缓存
    _loaded_modules: Dict[str, ModuleType] = {}
    # 已挂载的路由追踪
    _mounted_routers: Dict[str, List[APIRouter]] = {}

    @classmethod
    def get_plugin_dir(cls, plugin_key: str) -> Path:
        """获取插件目录"""
        return cls.PLUGINS_ROOT / plugin_key

    @classmethod
    def get_manifest_path(cls, plugin_key: str) -> Path:
        """获取插件 manifest.json 路径"""
        return cls.get_plugin_dir(plugin_key) / "manifest.json"

    @classmethod
    def get_frontend_bundle_path(cls, plugin_key: str, entry: Optional[str] = None) -> Path:
        """获取前端 bundle 路径"""
        plugin_dir = cls.get_plugin_dir(plugin_key)
        if entry:
            return plugin_dir / entry
        # 默认位置
        return plugin_dir / "frontend" / "index.js"

    @classmethod
    def get_asset_path(cls, plugin_key: str, asset_path: str) -> Path:
        """获取静态资源路径"""
        return cls.get_plugin_dir(plugin_key) / asset_path

    # ========== 解包和验证 ==========

    @classmethod
    def validate_manifest(cls, manifest_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """验证 manifest 数据"""
        errors: List[str] = []

        # 必需字段检查
        if not manifest_data.get("key"):
            errors.append("manifest 缺少必需字段: key")
        if not manifest_data.get("name"):
            errors.append("manifest 缺少必需字段: name")

        # key 格式检查（Java 命名空间格式）
        key = manifest_data.get("key", "")
        if key:
            import re

            # 格式: com.example.plugin (至少两级，每级以小写字母开头，可包含小写字母和数字)
            if not re.match(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)+$", key):
                errors.append(
                    "key 格式无效：必须使用命名空间格式（如 com.example.plugin），"
                    "每个部分以小写字母开头，只能包含小写字母和数字，至少两级"
                )

        # 版本格式检查（简单检查）
        version = manifest_data.get("version", "")
        if version and not isinstance(version, str):
            errors.append("version 必须是字符串")

        # 验证 frontend 配置
        frontend = manifest_data.get("frontend")
        if frontend and isinstance(frontend, dict):
            if frontend.get("entry") and not isinstance(frontend["entry"], str):
                errors.append("frontend.entry 必须是字符串")
            if frontend.get("styles") is not None:
                if not isinstance(frontend["styles"], list) or not all(
                    isinstance(x, str) for x in frontend["styles"]
                ):
                    errors.append("frontend.styles 必须是字符串数组")
            supported_exts = frontend.get("supportedExts") or frontend.get("supported_exts")
            if supported_exts and not isinstance(supported_exts, list):
                errors.append("frontend.supportedExts 必须是数组")
            use_system_window = frontend.get("useSystemWindow") or frontend.get("use_system_window")
            if use_system_window is not None and not isinstance(use_system_window, bool):
                errors.append("frontend.useSystemWindow 必须是布尔值")

        # 验证 backend 配置
        backend = manifest_data.get("backend")
        if backend and isinstance(backend, dict):
            routes = backend.get("routes", [])
            if routes:
                for i, route in enumerate(routes):
                    if not route.get("module"):
                        errors.append(f"backend.routes[{i}] 缺少 module")
                    if not route.get("prefix"):
                        errors.append(f"backend.routes[{i}] 缺少 prefix")

            processors = backend.get("processors", [])
            if processors:
                for i, proc in enumerate(processors):
                    if not proc.get("module"):
                        errors.append(f"backend.processors[{i}] 缺少 module")
                    if not proc.get("type"):
                        errors.append(f"backend.processors[{i}] 缺少 type")

        return len(errors) == 0, errors

    @classmethod
    def unpack_foxpkg(
        cls, file_content: bytes, target_key: Optional[str] = None
    ) -> Tuple[PluginManifest, Path]:
        """
        解包 .foxpkg 文件

        Args:
            file_content: .foxpkg 文件内容
            target_key: 可选，指定安装的插件 key（覆盖 manifest 中的 key）

        Returns:
            (manifest, plugin_dir) 元组

        Raises:
            PluginLoadError: 解包或验证失败
        """
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
                # 读取 manifest.json
                try:
                    manifest_bytes = zf.read("manifest.json")
                except KeyError:
                    raise PluginLoadError("插件包缺少 manifest.json")

                try:
                    manifest_data = json.loads(manifest_bytes.decode("utf-8"))
                except json.JSONDecodeError as e:
                    raise PluginLoadError(f"manifest.json 解析失败: {e}")

                # 验证 manifest
                valid, errors = cls.validate_manifest(manifest_data)
                if not valid:
                    raise PluginLoadError(f"manifest 验证失败: {'; '.join(errors)}")

                # 解析 manifest
                try:
                    manifest = PluginManifest.model_validate(manifest_data)
                except Exception as e:
                    raise PluginLoadError(f"manifest 解析失败: {e}")

                # 确定插件 key
                plugin_key = target_key or manifest.key

                # 验证包内文件
                cls._validate_package_files(zf, manifest)

                # 部署文件
                target_dir = cls.PLUGINS_ROOT / plugin_key
                if target_dir.exists():
                    # 备份旧版本
                    backup_dir = cls.PLUGINS_ROOT / f"{plugin_key}.backup"
                    if backup_dir.exists():
                        shutil.rmtree(backup_dir)
                    shutil.move(str(target_dir), str(backup_dir))

                target_dir.mkdir(parents=True, exist_ok=True)

                try:
                    zf.extractall(target_dir)
                except Exception as e:
                    # 恢复备份
                    if (cls.PLUGINS_ROOT / f"{plugin_key}.backup").exists():
                        shutil.rmtree(target_dir, ignore_errors=True)
                        shutil.move(str(cls.PLUGINS_ROOT / f"{plugin_key}.backup"), str(target_dir))
                    raise PluginLoadError(f"文件解压失败: {e}")

                # 清理备份
                backup_dir = cls.PLUGINS_ROOT / f"{plugin_key}.backup"
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)

                return manifest, target_dir

        except zipfile.BadZipFile:
            raise PluginLoadError("无效的插件包格式（非 ZIP 文件）")

    @classmethod
    def _validate_package_files(cls, zf: zipfile.ZipFile, manifest: PluginManifest) -> None:
        """验证包内文件是否完整"""
        file_list = zf.namelist()

        # 检查前端入口
        if manifest.frontend and manifest.frontend.entry:
            if manifest.frontend.entry not in file_list:
                raise PluginLoadError(f"前端入口文件不存在: {manifest.frontend.entry}")

        # 检查后端模块
        if manifest.backend:
            if manifest.backend.routes:
                for route in manifest.backend.routes:
                    if route.module not in file_list:
                        raise PluginLoadError(f"路由模块不存在: {route.module}")

            if manifest.backend.processors:
                for proc in manifest.backend.processors:
                    if proc.module not in file_list:
                        raise PluginLoadError(f"处理器模块不存在: {proc.module}")

    # ========== 路由动态加载 ==========

    @classmethod
    def load_route_module(cls, plugin_key: str, route_config: ManifestRouteConfig) -> APIRouter:
        """
        动态加载插件路由模块

        Args:
            plugin_key: 插件标识
            route_config: 路由配置

        Returns:
            加载的 APIRouter
        """
        module_path = cls.get_plugin_dir(plugin_key) / route_config.module

        if not module_path.exists():
            raise PluginLoadError(f"路由模块不存在: {module_path}")

        module_name = f"foxel_plugin_{plugin_key}_route_{module_path.stem}"

        try:
            spec = spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"无法加载路由模块: {module_path}")

            module = module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 缓存模块
            cls._loaded_modules[f"{plugin_key}:route:{route_config.module}"] = module

            # 获取 router
            router = getattr(module, "router", None)
            if router is None:
                raise PluginLoadError(f"路由模块缺少 'router' 对象: {module_path}")

            if not isinstance(router, APIRouter):
                raise PluginLoadError(f"'router' 不是有效的 APIRouter 实例: {module_path}")

            # 创建包装路由器添加前缀
            wrapper = APIRouter(prefix=route_config.prefix, tags=route_config.tags or [])
            wrapper.include_router(router)

            return wrapper

        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(f"加载路由模块失败 [{module_path}]: {e}")

    @classmethod
    def load_all_routes(cls, plugin_key: str, manifest: PluginManifest) -> List[APIRouter]:
        """加载插件的所有路由"""
        routers: List[APIRouter] = []

        if not manifest.backend or not manifest.backend.routes:
            return routers

        for route_config in manifest.backend.routes:
            router = cls.load_route_module(plugin_key, route_config)
            routers.append(router)

        cls._mounted_routers[plugin_key] = routers
        return routers

    # ========== 处理器动态注册 ==========

    @classmethod
    def load_processor_module(
        cls, plugin_key: str, processor_config: ManifestProcessorConfig
    ) -> None:
        """
        动态加载并注册处理器模块

        Args:
            plugin_key: 插件标识
            processor_config: 处理器配置
        """
        module_path = cls.get_plugin_dir(plugin_key) / processor_config.module

        if not module_path.exists():
            raise PluginLoadError(f"处理器模块不存在: {module_path}")

        module_name = f"foxel_plugin_{plugin_key}_processor_{module_path.stem}"

        try:
            spec = spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"无法加载处理器模块: {module_path}")

            module = module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 缓存模块
            cls._loaded_modules[f"{plugin_key}:processor:{processor_config.module}"] = module

            # 获取处理器工厂
            factory = getattr(module, "PROCESSOR_FACTORY", None)
            if factory is None:
                raise PluginLoadError(f"处理器模块缺少 'PROCESSOR_FACTORY': {module_path}")

            # 获取配置 schema
            config_schema = getattr(module, "CONFIG_SCHEMA", [])
            processor_name = getattr(module, "PROCESSOR_NAME", processor_config.name or processor_config.type)
            supported_exts = getattr(module, "SUPPORTED_EXTS", [])

            # 注册到处理器注册表
            from domain.processors import CONFIG_SCHEMAS, TYPE_MAP

            processor_type = processor_config.type
            TYPE_MAP[processor_type] = factory

            # 获取实例以读取属性
            try:
                sample = factory()
                produces_file = getattr(sample, "produces_file", False)
                supports_directory = getattr(sample, "supports_directory", False)
            except Exception:
                produces_file = False
                supports_directory = False

            CONFIG_SCHEMAS[processor_type] = {
                "type": processor_type,
                "name": processor_name,
                "supported_exts": supported_exts,
                "config_schema": config_schema,
                "produces_file": produces_file,
                "supports_directory": supports_directory,
                "plugin": plugin_key,  # 标记来源插件
                "module_path": str(module_path),
            }

        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(f"加载处理器模块失败 [{module_path}]: {e}")

    @classmethod
    def load_all_processors(cls, plugin_key: str, manifest: PluginManifest) -> List[str]:
        """加载插件的所有处理器，返回处理器类型列表"""
        processor_types: List[str] = []

        if not manifest.backend or not manifest.backend.processors:
            return processor_types

        for proc_config in manifest.backend.processors:
            cls.load_processor_module(plugin_key, proc_config)
            processor_types.append(proc_config.type)

        return processor_types

    # ========== 卸载 ==========

    @classmethod
    def unload_plugin(cls, plugin_key: str, manifest: Optional[PluginManifest] = None) -> None:
        """
        卸载插件的后端组件

        Args:
            plugin_key: 插件标识
            manifest: 可选的 manifest，用于确定要卸载的组件
        """
        # 卸载处理器
        if manifest and manifest.backend and manifest.backend.processors:
            from domain.processors import CONFIG_SCHEMAS, TYPE_MAP

            for proc_config in manifest.backend.processors:
                proc_type = proc_config.type
                if proc_type in TYPE_MAP:
                    del TYPE_MAP[proc_type]
                if proc_type in CONFIG_SCHEMAS:
                    del CONFIG_SCHEMAS[proc_type]

        # 清理缓存的模块
        keys_to_remove = [k for k in cls._loaded_modules if k.startswith(f"{plugin_key}:")]
        for key in keys_to_remove:
            module = cls._loaded_modules.pop(key, None)
            if module and module.__name__ in sys.modules:
                del sys.modules[module.__name__]

        # 清理路由追踪（注意：FastAPI 不支持动态移除路由，需要重启应用）
        cls._mounted_routers.pop(plugin_key, None)

    @classmethod
    def delete_plugin_files(cls, plugin_key: str) -> None:
        """删除插件文件"""
        plugin_dir = cls.get_plugin_dir(plugin_key)
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        # 同时删除备份
        backup_dir = cls.PLUGINS_ROOT / f"{plugin_key}.backup"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

    # ========== 读取 manifest ==========

    @classmethod
    def read_manifest(cls, plugin_key: str) -> Optional[PluginManifest]:
        """从文件系统读取插件 manifest"""
        manifest_path = cls.get_manifest_path(plugin_key)
        if not manifest_path.exists():
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PluginManifest.model_validate(data)
        except Exception:
            return None
