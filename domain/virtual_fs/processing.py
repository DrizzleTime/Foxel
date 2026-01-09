from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response

from .transfer import VirtualFSTransferMixin


class VirtualFSProcessingMixin(VirtualFSTransferMixin):
    @classmethod
    async def process_file(
        cls,
        path: str,
        processor_type: str,
        config: dict,
        save_to: str | None = None,
        overwrite: bool = False,
    ) -> Any:
        from domain.processors import get_processor

        processor = get_processor(processor_type)
        if not processor:
            raise HTTPException(400, detail=f"Processor {processor_type} not found")

        actual_is_dir = await cls.path_is_directory(path)
        requires_input_bytes = bool(getattr(processor, "requires_input_bytes", True))
        if actual_is_dir and bool(getattr(processor, "supports_directory", False)):
            if save_to:
                raise HTTPException(400, detail="Directory processing does not support custom save_to path")
            return await processor.process(b"", path, config)

        supported_exts = getattr(processor, "supported_exts", None) or []
        allowed_exts = {str(ext).lower().lstrip(".") for ext in supported_exts if isinstance(ext, str)}

        def matches_extension(rel_path: str) -> bool:
            if not allowed_exts:
                return True
            if "." not in rel_path:
                return "" in allowed_exts
            ext = rel_path.rsplit(".", 1)[-1].lower()
            return ext in allowed_exts or f".{ext}" in allowed_exts

        def coerce_result_bytes(result: Any) -> bytes:
            if isinstance(result, Response):
                return result.body
            if isinstance(result, (bytes, bytearray)):
                return bytes(result)
            if isinstance(result, str):
                return result.encode("utf-8")
            raise HTTPException(500, detail="Processor must return bytes/Response when produces_file=True")

        if actual_is_dir:
            if save_to:
                raise HTTPException(400, detail="Directory processing does not support custom save_to path")
            if not overwrite:
                raise HTTPException(400, detail="Directory processing requires overwrite")

            adapter_instance, adapter_model, root, rel = await cls.resolve_adapter_and_rel(path)
            rel = rel.rstrip("/")
            list_dir = await cls._ensure_method(adapter_instance, "list_dir")
            processed_count = 0
            stack: list[str] = [rel]
            page_size = 200

            while stack:
                current = stack.pop()
                page = 1
                while True:
                    entries, total = await list_dir(root, current, page, page_size, "name", "asc")
                    if not entries and (total or 0) == 0:
                        break

                    for entry in entries:
                        name = entry.get("name")
                        if not name:
                            continue
                        child_rel = f"{current}/{name}" if current else name
                        if entry.get("is_dir"):
                            stack.append(child_rel)
                            continue
                        if not matches_extension(child_rel):
                            continue
                        absolute_path = cls._build_absolute_path(adapter_model.path, child_rel)
                        data = b""
                        if requires_input_bytes:
                            data = await cls.read_file(absolute_path)
                        result = await processor.process(data, absolute_path, config)
                        if getattr(processor, "produces_file", False):
                            result_bytes = coerce_result_bytes(result)
                            await cls.write_file(absolute_path, result_bytes)
                        processed_count += 1

                    if total is None or page * page_size >= total:
                        break
                    page += 1

            return {"processed_files": processed_count}

        data = b""
        if requires_input_bytes:
            data = await cls.read_file(path)
        result = await processor.process(data, path, config)

        target_path = save_to
        if overwrite and not target_path:
            target_path = path

        if target_path and getattr(processor, "produces_file", False):
            result_bytes = coerce_result_bytes(result)
            await cls.write_file(target_path, result_bytes)
            return {"saved_to": target_path}

        return result
