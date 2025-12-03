import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import include_routers
from application.config.dependencies import config_service
from application.middleware.exception_handler import global_exception_handler
from application.middleware.logging_middleware import LoggingMiddleware
from application.task_queue import task_queue_service
from core.version import VERSION
from db.session import close_db, init_db
from infrastructure.storage_adapters.registry import runtime_registry

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data/db", exist_ok=True)
    await init_db()
    await runtime_registry.refresh()
    await config_service.set("APP_VERSION", VERSION)
    await task_queue_service.start_worker()
    try:
        yield
    finally:
        await task_queue_service.stop_worker()
        await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Foxel",
        description="A highly extensible private cloud storage solution for individuals and teams",
        lifespan=lifespan,
    )
    include_routers(app)
    app.add_middleware(LoggingMiddleware)
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
