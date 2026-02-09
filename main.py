import os
from pathlib import Path
from contextlib import asynccontextmanager

from domain.adapters import runtime_registry
from domain.config import ConfigService, VERSION
from db.session import close_db, init_db
from api.routers import include_routers
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from middleware.exception_handler import (
    global_exception_handler,
    http_exception_handler,
    httpx_exception_handler,
    validation_exception_handler,
)
import httpx
from dotenv import load_dotenv
from domain.tasks import task_queue_service, task_scheduler
from domain.role.service import RoleService

load_dotenv()


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            if self._should_spa_fallback(scope):
                return FileResponse(INDEX_FILE)
            raise

        if response.status_code == 404 and self._should_spa_fallback(scope):
            return FileResponse(INDEX_FILE)
        return response

    @staticmethod
    def _should_spa_fallback(scope) -> bool:
        return (
            scope.get("method") == "GET"
            and _request_accepts_html(scope)
            and not (scope.get("path") or "").startswith(SPA_EXCLUDE_PREFIXES)
            and INDEX_FILE.exists()
        )


INDEX_FILE = Path("web/dist/index.html")
SPA_EXCLUDE_PREFIXES = ("/api", "/docs", "/openapi.json", "/webdav", "/s3")


def _request_accepts_html(scope) -> bool:
    for k, v in scope.get("headers") or []:
        if k == b"accept":
            return "text/html" in v.decode("latin-1")
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data/db", exist_ok=True)
    os.makedirs("data/plugins", exist_ok=True)
    await init_db()
    await RoleService.ensure_system_roles()
    await runtime_registry.refresh()
    await ConfigService.set("APP_VERSION", VERSION)
    await task_queue_service.start_worker()

    # 加载已安装的插件
    from domain.plugins import init_plugins
    await init_plugins(app)
    await task_scheduler.start()

    # 在所有路由加载完成后，挂载静态文件服务（放在最后以避免覆盖 API 路由）
    app.mount("/", SPAStaticFiles(directory="web/dist", html=True, check_dir=False), name="static")

    try:
        yield
    finally:
        await task_scheduler.stop()
        await task_queue_service.stop_worker()
        await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Foxel",
        description="A highly extensible private cloud storage solution for individuals and teams",
        lifespan=lifespan,
    )
    include_routers(app)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(httpx.HTTPStatusError, httpx_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    return app


app = create_app()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
