import inspect
import pkgutil
from importlib import import_module
from typing import Callable, Dict

from models import StorageAdapter
from domain.adapters.providers.base import BaseAdapter

AdapterFactory = Callable[[StorageAdapter], BaseAdapter]

TYPE_MAP: Dict[str, AdapterFactory] = {}
CONFIG_SCHEMAS: Dict[str, list] = {}


def normalize_adapter_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def discover_adapters():
    """扫描 domain.adapters.providers 包, 自动注册适配器类型、工厂与配置 schema。"""
    from domain.adapters import providers as adapters_pkg

    TYPE_MAP.clear()
    CONFIG_SCHEMAS.clear()
    for modinfo in pkgutil.iter_modules(adapters_pkg.__path__):
        if modinfo.name.startswith("_"):
            continue
        full_name = f"{adapters_pkg.__name__}.{modinfo.name}"
        try:
            module = import_module(full_name)
        except Exception:
            continue

        adapter_types = getattr(module, "ADAPTER_TYPES", None)
        if isinstance(adapter_types, dict):
            default_schema = getattr(module, "CONFIG_SCHEMA", None)
            schema_map = getattr(module, "CONFIG_SCHEMA_MAP", None)
            if not isinstance(schema_map, dict):
                schema_map = None

            for adapter_type, factory in adapter_types.items():
                normalized_type = normalize_adapter_type(adapter_type)
                if not normalized_type:
                    continue
                if not callable(factory):
                    continue
                TYPE_MAP[normalized_type] = factory

                schema = schema_map.get(normalized_type) if schema_map else default_schema
                if isinstance(schema, list):
                    CONFIG_SCHEMAS[normalized_type] = schema
            continue

        adapter_type = normalize_adapter_type(getattr(module, "ADAPTER_TYPE", None))
        schema = getattr(module, "CONFIG_SCHEMA", None)
        factory = getattr(module, "ADAPTER_FACTORY", None)

        if not adapter_type:
            continue

        if factory is None:
            for attr in module.__dict__.values():
                if inspect.isclass(attr) and attr.__name__.endswith("Adapter"):
                    def _mk(cls=attr):
                        return lambda rec: cls(rec)
                    factory = _mk()
                    break
        if not callable(factory):
            continue

        TYPE_MAP[adapter_type] = factory
        if isinstance(schema, list):
            CONFIG_SCHEMAS[adapter_type] = schema


def get_config_schemas() -> Dict[str, list]:
    return CONFIG_SCHEMAS


def get_config_schema(adapter_type: str):
    return CONFIG_SCHEMAS.get(adapter_type)


class RuntimeRegistry:
    def __init__(self):
        self._instances: Dict[int, BaseAdapter] = {}

    async def refresh(self):
        discover_adapters()
        self._instances.clear()
        adapters = await StorageAdapter.filter(enabled=True)
        for rec in adapters:
            normalized_type = normalize_adapter_type(rec.type)
            if not normalized_type:
                continue
            if normalized_type != rec.type:
                rec.type = normalized_type
                try:
                    await rec.save(update_fields=["type"])
                except Exception:
                    continue
            factory = TYPE_MAP.get(normalized_type)
            if not factory:
                continue
            try:
                self._instances[rec.id] = factory(rec)
            except Exception:
                continue

    def get(self, adapter_id: int) -> BaseAdapter | None:
        return self._instances.get(adapter_id)

    def snapshot(self) -> Dict[int, BaseAdapter]:
        return dict(self._instances)

    def remove(self, adapter_id: int):
        """从缓存中移除一个适配器实例"""
        if adapter_id in self._instances:
            del self._instances[adapter_id]

    async def upsert(self, rec: StorageAdapter):
        """新增或更新一个适配器实例"""
        if not rec.enabled:
            self.remove(rec.id)
            return

        normalized_type = normalize_adapter_type(rec.type)
        if not normalized_type:
            self.remove(rec.id)
            return
        if normalized_type != rec.type:
            rec.type = normalized_type
            try:
                await rec.save(update_fields=["type"])
            except Exception:
                pass

        factory = TYPE_MAP.get(normalized_type)
        if not factory:
            discover_adapters()
            factory = TYPE_MAP.get(normalized_type)
            if not factory:
                return

        try:
            instance = factory(rec)
            self._instances[rec.id] = instance
        except Exception:
            self.remove(rec.id)
            pass


runtime_registry = RuntimeRegistry()
discover_adapters()
