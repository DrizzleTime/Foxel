"""Plugin route ownership and dispatch, independent of the application entry point."""
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

    def replace_routes(self, key: str, routers: list[APIRouter]):
        combined = APIRouter()
        for router in routers:
            combined.include_router(router)
        self.routers = {**self.routers, key: combined}

    def remove(self, key: str):
        self.routers = {k: v for k, v in self.routers.items() if k != key}


def get_plugin_manager(request: Request) -> PluginManager:
    return request.app.state.plugin_manager
