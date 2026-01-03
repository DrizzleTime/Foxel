from fastapi import FastAPI

from domain.adapters import api as adapters
from domain.auth import api as auth
from domain.backup import api as backup
from domain.config import api as config
from domain.email import api as email
from domain.offline_downloads import api as offline_downloads
from domain.plugins import api as plugins
from domain.processors import api as processors
from domain.share import api as share
from domain.tasks import api as tasks
from domain.ai import api as ai
from domain.virtual_fs import api as virtual_fs
from domain.virtual_fs.mapping import s3_api, webdav_api
from domain.virtual_fs.search import search_api
from domain.audit import router as audit


def include_routers(app: FastAPI):
    app.include_router(adapters.router)
    app.include_router(search_api.router)
    app.include_router(virtual_fs.router)
    app.include_router(auth.router)
    app.include_router(config.router)
    app.include_router(processors.router)
    app.include_router(tasks.router)
    app.include_router(share.router)
    app.include_router(share.public_router)
    app.include_router(backup.router)
    app.include_router(ai.router_vector_db)
    app.include_router(ai.router_ai)
    app.include_router(plugins.router)
    app.include_router(webdav_api.router)
    app.include_router(s3_api.router)
    app.include_router(offline_downloads.router)
    app.include_router(email.router)
    app.include_router(audit)
