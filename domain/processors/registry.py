import sys
from dataclasses import dataclass

import inspect
import pkgutil
from importlib import import_module, reload
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, Optional

from .base import BaseProcessor

ProcessorFactory = Callable[[], BaseProcessor]
TYPE_MAP: Dict[str, ProcessorFactory] = {}
CONFIG_SCHEMAS: Dict[str, dict] = {}
MODULE_MAP: Dict[str, ModuleType] = {}
LAST_DISCOVERY_ERRORS: list[str] = []


@dataclass(frozen=True)
class ProcessorRegistration:
    owner: str
    version: str
    factory: ProcessorFactory
    metadata: dict
    module: ModuleType


REGISTRATIONS: dict[str, ProcessorRegistration] = {}


def validate_registration(processor_type: str, owner: str):
    existing = REGISTRATIONS.get(processor_type)
    if existing and existing.owner != owner:
        raise ValueError(f"处理器 {processor_type} 已由 {existing.owner} 注册")
    if processor_type in TYPE_MAP and existing is None:
        raise ValueError(f"处理器 {processor_type} 已注册且归属未知")


def register(processor_type: str, *, owner: str, version: str, factory: ProcessorFactory,
             metadata: dict, module: ModuleType):
    validate_registration(processor_type, owner)
    if not callable(factory):
        raise ValueError(f"处理器 {processor_type} 缺少有效工厂")
    REGISTRATIONS[processor_type] = ProcessorRegistration(owner, version, factory, metadata, module)
    TYPE_MAP[processor_type] = factory
    CONFIG_SCHEMAS[processor_type] = {**metadata, "owner": owner, "version": version}
    MODULE_MAP[processor_type] = module


def unregister_owner(owner: str):
    for processor_type, registration in list(REGISTRATIONS.items()):
        if registration.owner == owner:
            REGISTRATIONS.pop(processor_type)
            TYPE_MAP.pop(processor_type, None)
            CONFIG_SCHEMAS.pop(processor_type, None)
            MODULE_MAP.pop(processor_type, None)


def discover_processors(force_reload: bool = False) -> list[str]:
    """扫描并缓存可用的处理器模块。"""
    from . import builtin as processors_pkg

    global LAST_DISCOVERY_ERRORS
    LAST_DISCOVERY_ERRORS = []

    for modinfo in pkgutil.iter_modules(processors_pkg.__path__):
        if modinfo.name.startswith("_"):
            continue

        full_name = f"{processors_pkg.__name__}.{modinfo.name}"
        try:
            module = import_module(full_name)
            if force_reload:
                module = reload(module)
        except Exception as exc:
            LAST_DISCOVERY_ERRORS.append(f"Failed to import {full_name}: {exc}")
            continue

        processor_type = getattr(module, "PROCESSOR_TYPE", None)
        processor_name = getattr(module, "PROCESSOR_NAME", None)
        supported_exts = getattr(module, "SUPPORTED_EXTS", None)
        schema = getattr(module, "CONFIG_SCHEMA", None)
        factory = getattr(module, "PROCESSOR_FACTORY", None)

        if not processor_type:
            continue

        if factory is None:
            for attr in module.__dict__.values():
                if inspect.isclass(attr) and attr.__name__.endswith("Processor"):

                    def _mk(cls=attr):
                        return lambda: cls()

                    factory = _mk()
                    break

        if not callable(factory):
            LAST_DISCOVERY_ERRORS.append(f"Processor {full_name} missing factory")
            continue

        try:
            sample = factory()
        except Exception as exc:
            LAST_DISCOVERY_ERRORS.append(f"Failed to instantiate processor {processor_type}: {exc}")
            continue

        produces_file = getattr(module, "produces_file", None)
        if produces_file is None and hasattr(sample, "produces_file"):
            produces_file = getattr(sample, "produces_file")

        supports_directory = getattr(module, "supports_directory", None)
        if supports_directory is None and hasattr(sample, "supports_directory"):
            supports_directory = getattr(sample, "supports_directory")

        module_file = getattr(module, "__file__", None)
        module_path: Optional[str] = None
        if module_file:
            try:
                module_path = str(Path(module_file).resolve())
            except Exception:
                module_path = module_file

        if isinstance(supported_exts, list):
            normalized_exts = [str(ext) for ext in supported_exts]
        elif supported_exts:
            normalized_exts = [str(supported_exts)]
        else:
            normalized_exts = []

        if not normalized_exts and hasattr(sample, "supported_exts"):
            sample_exts = getattr(sample, "supported_exts") or []
            if isinstance(sample_exts, list):
                normalized_exts = [str(ext) for ext in sample_exts]

        if isinstance(schema, list):
            metadata = {
                "type": processor_type,
                "name": processor_name or processor_type,
                "supported_exts": normalized_exts,
                "config_schema": schema,
                "produces_file": produces_file if produces_file is not None else False,
                "supports_directory": supports_directory if supports_directory is not None else False,
                "module_path": module_path,
            }

            try:
                register(processor_type, owner="builtin", version="host", factory=factory,
                         metadata=metadata, module=module)
            except ValueError as exc:
                LAST_DISCOVERY_ERRORS.append(str(exc))

    if force_reload:
        from domain.plugins.loader import PluginLoader
        from domain.plugins.types import ManifestProcessorConfig
        for processor_type, registration in list(REGISTRATIONS.items()):
            if registration.owner == "builtin":
                continue
            cache = dict(PluginLoader._loaded_modules)
            try:
                metadata = registration.metadata
                path = Path(metadata["module_path"])
                prepared = PluginLoader.load_processor_module(
                    registration.owner,
                    ManifestProcessorConfig(module=metadata.get("module", path.name), type=processor_type, name=metadata.get("name")),
                    Path(metadata.get("plugin_directory", path.parent)), register=False,
                )
                _, factory, meta, module = prepared
                register(processor_type, owner=registration.owner, version=registration.version,
                         factory=factory, metadata=meta, module=module)
                for key, cached_module in list(PluginLoader._loaded_modules.items()):
                    if cached_module is registration.module:
                        del PluginLoader._loaded_modules[key]
                sys.modules.pop(registration.module.__name__, None)
            except Exception as exc:
                for key, candidate in list(PluginLoader._loaded_modules.items()):
                    if key.startswith(f"{registration.owner}:") and cache.get(key) is not candidate:
                        sys.modules.pop(candidate.__name__, None)
                        PluginLoader._loaded_modules.pop(key, None)
                PluginLoader._loaded_modules.update(cache)
                LAST_DISCOVERY_ERRORS.append(f"Failed to reload {processor_type}: {exc}")
    return LAST_DISCOVERY_ERRORS


def get_config_schemas() -> Dict[str, dict]:
    return CONFIG_SCHEMAS


def get_config_schema(processor_type: str):
    return CONFIG_SCHEMAS.get(processor_type)


def get(processor_type: str) -> BaseProcessor | None:
    factory = TYPE_MAP.get(processor_type)
    if factory:
        return factory()
    return None


def get_module_path(processor_type: str) -> Optional[str]:
    meta = CONFIG_SCHEMAS.get(processor_type)
    if not meta:
        return None
    return meta.get("module_path")


def get_last_discovery_errors() -> list[str]:
    return LAST_DISCOVERY_ERRORS


def reload_processors() -> list[str]:
    return discover_processors(force_reload=True)


discover_processors()
