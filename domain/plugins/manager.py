"""Plugin route ownership and dispatch, independent of the application entry point."""
import asyncio
import sys

from fastapi import APIRouter, Request
from starlette.routing import BaseRoute, Match


class PluginDispatch(BaseRoute):
    def __init__(self, manager: "PluginManager"):
        self.manager = manager

    def matches(self, scope):
        partial = None
        for router in tuple(self.manager.routers.values()):
            for route in router.routes:
                match, child = route.matches(scope)
                if match == Match.FULL:
                    return match, {**child, "plugin_route": route}
                if match == Match.PARTIAL and partial is None:
                    partial = (match, {**child, "plugin_route": route})
        return partial or (Match.NONE, {})

    async def handle(self, scope, receive, send):
        await scope["plugin_route"].handle(scope, receive, send)

    def url_path_for(self, name, /, **path_params):
        from starlette.routing import NoMatchFound
        for router in tuple(self.manager.routers.values()):
            try:
                return router.url_path_for(name, **path_params)
            except NoMatchFound:
                pass
        raise NoMatchFound(name, path_params)


class PluginManager:
    def __init__(self):
        self.routers: dict[str, APIRouter] = {}
        self.dispatch = PluginDispatch(self)
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, key: str):
        return self._locks.setdefault(key, asyncio.Lock())

    def snapshot(self, key: str, manifest):
        from .loader import PluginLoader
        from domain.processors.registry import REGISTRATIONS
        return (
            self.routers.get(key),
            {k: v for k, v in PluginLoader._loaded_modules.items() if k.startswith(f"{key}:")},
            {t: r for t, r in REGISTRATIONS.items() if r.owner == key},
        )

    def restore(self, key, snapshot):
        from .loader import PluginLoader
        from domain.processors.registry import register, unregister_owner
        router, modules, processors = snapshot
        self.remove(key)
        if router is not None:
            self.routers = {**self.routers, key: router}
        self.clean_modules(key, keep=modules.values())
        PluginLoader._loaded_modules.update(modules)
        unregister_owner(key)
        for t, registration in processors.items():
            register(t, owner=key, version=registration.version, factory=registration.factory,
                     metadata=registration.metadata, module=registration.module)

    def clean_modules(self, key, keep=()):
        from .loader import PluginLoader
        keep = set(keep)
        for name, module in list(PluginLoader._loaded_modules.items()):
            if name.startswith(f"{key}:") and module not in keep:
                sys.modules.pop(module.__name__, None)
                del PluginLoader._loaded_modules[name]

    def prepare(self, key, manifest, directory):
        from .compatibility import check_compatibility
        check_compatibility(manifest)
        from .loader import PluginLoader
        routers = PluginLoader.load_all_routes(key, manifest, directory)
        processors = [
            PluginLoader.load_processor_module(key, config, directory, register=False)
            for config in (manifest.backend.processors or [] if manifest.backend else [])
        ]
        from domain.processors.registry import validate_registration
        types = [p[0] for p in processors]
        if len(types) != len(set(types)):
            raise ValueError("插件声明了重复的处理器类型")
        for processor_type in types:
            validate_registration(processor_type, key)
        return routers, processors, manifest.version

    def activate(self, key, prepared):
        from domain.processors.registry import register, unregister_owner, validate_registration
        routers, processors, version = prepared
        for t, *_ in processors:
            validate_registration(t, key)
        unregister_owner(key)
        for t, factory, metadata, module in processors:
            register(t, owner=key, version=version, factory=factory, metadata=metadata, module=module)
        self.replace_routes(key, routers)

    def replace_routes(self, key: str, routers: list[APIRouter]):
        combined = APIRouter()
        for router in routers:
            combined.include_router(router)
        self.routers = {**self.routers, key: combined}

    def remove(self, key: str):
        self.routers = {k: v for k, v in self.routers.items() if k != key}


def get_plugin_manager(request: Request) -> PluginManager:
    return request.app.state.plugin_manager
