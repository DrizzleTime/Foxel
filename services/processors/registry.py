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


def discover_processors(force_reload: bool = False) -> list[str]:
    """Discover available processor modules and cache their metadata."""
    import services.processors  # 延迟导入以避免循环

    processors_pkg = services.processors
    TYPE_MAP.clear()
    CONFIG_SCHEMAS.clear()
    MODULE_MAP.clear()

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

        TYPE_MAP[processor_type] = factory
        MODULE_MAP[processor_type] = module

        produces_file = getattr(module, "produces_file", None)
        if produces_file is None and hasattr(sample, "produces_file"):
            produces_file = getattr(sample, "produces_file")

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
            CONFIG_SCHEMAS[processor_type] = {
                "type": processor_type,
                "name": processor_name or processor_type,
                "supported_exts": normalized_exts,
                "config_schema": schema,
                "produces_file": produces_file if produces_file is not None else False,
                "module_path": module_path,
            }

    return LAST_DISCOVERY_ERRORS


def get_config_schemas() -> Dict[str, dict]:
    return CONFIG_SCHEMAS


def get_config_schema(processor_type: str):
    return CONFIG_SCHEMAS.get(processor_type)


def get(processor_type: str) -> BaseProcessor:
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
