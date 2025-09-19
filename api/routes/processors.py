from pathlib import Path
from fastapi import APIRouter, Depends, Body, HTTPException
from fastapi.concurrency import run_in_threadpool
from typing import Annotated
from services.processors.registry import (
    get_config_schemas,
    get_module_path,
    reload_processors,
)
from services.task_queue import task_queue_service
from services.auth import get_current_active_user, User
from api.response import success
from pydantic import BaseModel
from services.virtual_fs import path_is_directory

router = APIRouter(prefix="/api/processors", tags=["processors"])


@router.get("")
async def list_processors(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    schemas = get_config_schemas()
    out = []
    for t, meta in schemas.items():
        out.append({
            "type": meta["type"],
            "name": meta["name"],
            "supported_exts": meta.get("supported_exts", []),
            "config_schema": meta["config_schema"],
            "produces_file": meta.get("produces_file", False),
            "module_path": meta.get("module_path"),
        })
    return success(out)


class ProcessRequest(BaseModel):
    path: str
    processor_type: str
    config: dict
    save_to: str | None = None
    overwrite: bool = False


class UpdateSourceRequest(BaseModel):
    source: str


@router.post("/process")
async def process_file_with_processor(
    current_user: Annotated[User, Depends(get_current_active_user)],
    req: ProcessRequest = Body(...)
):
    is_dir = await path_is_directory(req.path)
    if is_dir and not req.overwrite:
        raise HTTPException(400, detail="Directory processing requires overwrite")

    save_to = None if is_dir else (req.path if req.overwrite else req.save_to)
    task = await task_queue_service.add_task(
        "process_file",
        {
            "path": req.path,
            "processor_type": req.processor_type,
            "config": req.config,
            "save_to": save_to,
            "overwrite": req.overwrite,
        },
    )
    return success({"task_id": task.id})


@router.get("/source/{processor_type}")
async def get_processor_source(
    processor_type: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    module_path = get_module_path(processor_type)
    if not module_path:
        raise HTTPException(404, detail="Processor not found")
    path_obj = Path(module_path)
    if not path_obj.exists():
        raise HTTPException(404, detail="Processor source not found")
    try:
        content = await run_in_threadpool(path_obj.read_text, encoding='utf-8')
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to read source: {exc}")
    return success({"source": content, "module_path": str(path_obj)})


@router.put("/source/{processor_type}")
async def update_processor_source(
    processor_type: str,
    req: UpdateSourceRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    module_path = get_module_path(processor_type)
    if not module_path:
        raise HTTPException(404, detail="Processor not found")
    path_obj = Path(module_path)
    if not path_obj.exists():
        raise HTTPException(404, detail="Processor source not found")
    try:
        await run_in_threadpool(path_obj.write_text, req.source, encoding='utf-8')
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to write source: {exc}")
    return success(True)


@router.post("/reload")
async def reload_processor_modules(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    errors = reload_processors()
    if errors:
        raise HTTPException(500, detail="; ".join(errors))
    return success(True)
