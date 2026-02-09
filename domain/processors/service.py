from pathlib import Path
from typing import List, Tuple

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from domain.tasks import task_queue_service
from domain.virtual_fs import VirtualFSService
from .registry import (
    get,
    get_config_schema,
    get_config_schemas,
    get_module_path,
    reload_processors,
)
from .types import (
    ProcessDirectoryRequest,
    ProcessRequest,
    UpdateSourceRequest,
)


class ProcessorService:
    @classmethod
    def get_processor(cls, processor_type: str):
        return get(processor_type)

    @classmethod
    def list_processors(cls):
        schemas = get_config_schemas()
        out = []
        for t, meta in schemas.items():
            out.append({
                "type": meta["type"],
                "name": meta["name"],
                "supported_exts": meta.get("supported_exts", []),
                "config_schema": meta["config_schema"],
                "produces_file": meta.get("produces_file", False),
                "supports_directory": meta.get("supports_directory", False),
                "module_path": meta.get("module_path"),
            })
        return out

    @classmethod
    async def process_file(cls, req: ProcessRequest):
        processor = cls.get_processor(req.processor_type)
        if not processor:
            raise HTTPException(404, detail="Processor not found")

        is_dir = await VirtualFSService.path_is_directory(req.path)
        supports_directory = bool(getattr(processor, "supports_directory", False))
        if is_dir and not supports_directory and not req.overwrite:
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
        return {"task_id": task.id}

    @classmethod
    async def process_directory(cls, req: ProcessDirectoryRequest):
        if req.max_depth is not None and req.max_depth < 0:
            raise HTTPException(400, detail="max_depth must be >= 0")

        is_dir = await VirtualFSService.path_is_directory(req.path)
        if not is_dir:
            raise HTTPException(400, detail="Path must be a directory")

        schema = get_config_schema(req.processor_type)
        _processor = get(req.processor_type)
        if not schema or not _processor:
            raise HTTPException(404, detail="Processor not found")

        produces_file = bool(schema.get("produces_file"))
        raw_suffix = req.suffix if req.suffix is not None else None
        if raw_suffix is not None and raw_suffix.strip() == "":
            raw_suffix = None
        suffix = raw_suffix
        overwrite = req.overwrite

        if produces_file:
            if not overwrite and not suffix:
                raise HTTPException(400, detail="Suffix is required when not overwriting files")
        else:
            overwrite = False
            suffix = None
        payload = {
            "path": req.path,
            "processor_type": req.processor_type,
            "config": req.config,
            "overwrite": overwrite,
            "max_depth": req.max_depth,
            "suffix": suffix,
        }
        task = await task_queue_service.add_task("process_directory_scan", payload)
        return {"task_id": task.id}

    @classmethod
    async def scan_directory(cls, req: ProcessDirectoryRequest):
        if req.max_depth is not None and req.max_depth < 0:
            raise HTTPException(400, detail="max_depth must be >= 0")

        is_dir = await VirtualFSService.path_is_directory(req.path)
        if not is_dir:
            raise HTTPException(400, detail="Path must be a directory")

        schema = get_config_schema(req.processor_type)
        _processor = get(req.processor_type)
        if not schema or not _processor:
            raise HTTPException(404, detail="Processor not found")

        produces_file = bool(schema.get("produces_file"))
        raw_suffix = req.suffix if req.suffix is not None else None
        if raw_suffix is not None and raw_suffix.strip() == "":
            raw_suffix = None
        suffix = raw_suffix
        overwrite = req.overwrite

        if produces_file:
            if not overwrite and not suffix:
                raise HTTPException(400, detail="Suffix is required when not overwriting files")
        else:
            overwrite = False
            suffix = None

        supported_exts = schema.get("supported_exts") or []
        allowed_exts = {
            ext.lower().lstrip('.')
            for ext in supported_exts
            if isinstance(ext, str)
        }

        def matches_extension(file_rel: str) -> bool:
            if not allowed_exts:
                return True
            if '.' not in file_rel:
                return '' in allowed_exts
            ext = file_rel.rsplit('.', 1)[-1].lower()
            return ext in allowed_exts or f'.{ext}' in allowed_exts

        adapter_instance, adapter_model, root, rel = await VirtualFSService.resolve_adapter_and_rel(req.path)
        rel = rel.rstrip('/')

        list_dir = getattr(adapter_instance, "list_dir", None)
        if not callable(list_dir):
            raise HTTPException(501, detail="Adapter does not implement list_dir")

        def build_absolute_path(mount_path: str, rel_path: str) -> str:
            rel_norm = rel_path.lstrip('/')
            mount_norm = mount_path.rstrip('/')
            if not mount_norm:
                return '/' + rel_norm if rel_norm else '/'
            return f"{mount_norm}/{rel_norm}" if rel_norm else mount_norm

        def apply_suffix(path_str: str, suffix_str: str) -> str:
            path_obj = Path(path_str)
            name = path_obj.name
            if not name:
                return path_str
            if '.' in name:
                base, ext = name.rsplit('.', 1)
                new_name = f"{base}{suffix_str}.{ext}"
            else:
                new_name = f"{name}{suffix_str}"
            return str(path_obj.with_name(new_name))

        scheduled_count = 0
        stack: List[Tuple[str, int]] = [(rel, 0)]
        page_size = 200

        while stack:
            current_rel, depth = stack.pop()
            page = 1
            while True:
                entries, total = await list_dir(root, current_rel, page, page_size, "name", "asc")
                entries = entries or []
                if not entries and (total or 0) == 0:
                    break

                for entry in entries:
                    name = entry.get("name")
                    if not name:
                        continue
                    child_rel = f"{current_rel}/{name}" if current_rel else name
                    if entry.get("is_dir"):
                        if req.max_depth is None or depth < req.max_depth:
                            stack.append((child_rel.rstrip('/'), depth + 1))
                        continue
                    if not matches_extension(child_rel):
                        continue
                    absolute_path = build_absolute_path(adapter_model.path, child_rel)
                    save_to = None
                    if produces_file and not overwrite and suffix:
                        save_to = apply_suffix(absolute_path, suffix)
                    await task_queue_service.add_task(
                        "process_file",
                        {
                            "path": absolute_path,
                            "processor_type": req.processor_type,
                            "config": req.config,
                            "save_to": save_to,
                            "overwrite": overwrite,
                        },
                    )
                    scheduled_count += 1

                if total is None or page * page_size >= total:
                    break
                page += 1

        return {"scheduled": scheduled_count}

    @classmethod
    async def get_source(cls, processor_type: str):
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
        return {"source": content, "module_path": str(path_obj)}

    @classmethod
    async def update_source(cls, processor_type: str, req: UpdateSourceRequest):
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
        return True

    @classmethod
    def reload(cls):
        errors = reload_processors()
        if errors:
            raise HTTPException(500, detail="; ".join(errors))
        return True


get_processor = ProcessorService.get_processor
list_processors = ProcessorService.list_processors
reload_processor_modules = ProcessorService.reload
