from typing import Any, Dict, Optional

from domain.processors import ProcessDirectoryRequest, ProcessRequest, ProcessorService
from domain.virtual_fs import VirtualFSService

from .base import ToolSpec
from domain.permission.execution import require_path
from domain.permission.types import PathAction


async def _processors_list(_: Dict[str, Any]) -> Dict[str, Any]:
    return {"processors": ProcessorService.list_processors()}


async def _processors_run(args: Dict[str, Any]) -> Dict[str, Any]:
    path = str(args.get("path") or "")
    path = await require_path(path, PathAction.READ)
    processor_type = str(args.get("processor_type") or "")
    config = args.get("config")
    if not isinstance(config, dict):
        config = {}

    save_to = args.get("save_to")
    save_to = str(save_to) if isinstance(save_to, str) and save_to.strip() else None

    max_depth = args.get("max_depth")
    max_depth_value: Optional[int] = None
    if max_depth is not None:
        try:
            max_depth_value = int(max_depth)
        except (TypeError, ValueError):
            max_depth_value = None

    suffix = args.get("suffix")
    suffix_value = str(suffix) if isinstance(suffix, str) and suffix.strip() else None

    overwrite_value = args.get("overwrite")
    overwrite = bool(overwrite_value) if overwrite_value is not None else None

    is_dir = await VirtualFSService.path_is_directory(path)
    if is_dir and (max_depth_value is not None or suffix_value is not None):
        req = ProcessDirectoryRequest(
            path=path,
            processor_type=processor_type,
            config=config,
            overwrite=True if overwrite is None else overwrite,
            max_depth=max_depth_value,
            suffix=suffix_value,
        )
        result = await ProcessorService.process_directory(req)
        return {"mode": "directory", **result}

    req = ProcessRequest(
        path=path,
        processor_type=processor_type,
        config=config,
        save_to=save_to,
        overwrite=False if overwrite is None else overwrite,
    )
    result = await ProcessorService.process_file(req)
    return {"mode": "file", **result}


TOOLS: Dict[str, ToolSpec] = {
    "processors_list": ToolSpec(
        name="processors_list",
        description=(
            "Use before watermarking images, converting files, or performing other processing tasks to discover available processors."
            " Returns type, name, supported_exts, config_schema, produces_file, and supports_directory."
            " Choose a listed processor_type compatible with the input, build config from config_schema, then call processors_run."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_processors_list,
    ),
    "processors_run": ToolSpec(
        name="processors_run",
        description=(
            "Submit a processing task for a Foxel file or directory, such as watermarking, conversion, or indexing;"
            " available capabilities are listed by processors_list. Check processor settings and formats first, and verify the input with vfs_stat."
            " For processors that produce files, preserve a single input with overwrite=false and save_to, or replace it with overwrite=true."
            " Set max_depth or suffix to enable per-file directory batching; max_depth=0 processes only the current level."
            " Batching defaults to overwrite=true; when producing files with overwrite=false, suffix is required to save copies."
            " Directories without max_depth/suffix use the processor's regular entry point, subject to supports_directory and overwrite."
            " A returned task_id means the task was submitted, not completed. Check results in the Foxel task queue."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute Foxel virtual file or directory path, e.g. /photos/image.jpg or /photos."},
                "processor_type": {"type": "string", "description": "A type returned by processors_list, e.g. image_watermark. Check supported formats and directory capabilities first."},
                "config": {"type": "object", "description": "Processor configuration following the config_schema returned by processors_list."},
                "overwrite": {"type": "boolean", "description": "Whether to replace input files. Defaults to false for single files and regular directory processing, true for directory batching with max_depth or suffix. Specify explicitly."},
                "save_to": {"type": "string", "description": "Full absolute Foxel output path for a single file with overwrite=false. Required when producing a file while preserving the input; invalid for directories."},
                "max_depth": {"type": "integer", "minimum": 0, "description": "Subdirectory depth for per-file batching: 0 for the current level, 1 to include one nested level. Omit for unlimited depth. Providing this enables directory batching."},
                "suffix": {"type": "string", "description": "Output filename suffix for directory batching, e.g. _watermarked creates photo_watermarked.jpg. Required when produces_file=true and overwrite=false. Must not contain path separators."},
            },
            "required": ["path", "processor_type"],
        },
        requires_confirmation=True,
        handler=_processors_run,
    ),
}
