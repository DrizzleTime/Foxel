import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from domain.processors.service import ProcessorService
from domain.processors.types import ProcessDirectoryRequest, ProcessRequest
from domain.virtual_fs.service import VirtualFSService


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    requires_confirmation: bool
    handler: Callable[[Dict[str, Any]], Awaitable[Any]]


async def _processors_list(_: Dict[str, Any]) -> Dict[str, Any]:
    return {"processors": ProcessorService.list_processors()}


async def _processors_run(args: Dict[str, Any]) -> Dict[str, Any]:
    path = str(args.get("path") or "")
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
        description="获取可用处理器列表（type/name/config_schema 等）。",
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
            "运行处理器处理文件或目录。"
            " 对目录可选 max_depth/suffix；对文件可选 overwrite/save_to。"
            " 返回任务 id（去任务队列查看进度）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径（绝对路径，如 /foo/bar）"},
                "processor_type": {"type": "string", "description": "处理器类型（例如 image_watermark）"},
                "config": {"type": "object", "description": "处理器配置，按 processors_list 返回的 config_schema 填写"},
                "overwrite": {"type": "boolean", "description": "是否覆盖原文件/目录内文件"},
                "save_to": {"type": "string", "description": "保存到指定路径（仅文件模式，且 overwrite=false 时使用）"},
                "max_depth": {"type": "integer", "description": "目录遍历深度（仅目录模式）"},
                "suffix": {"type": "string", "description": "目录批处理时的输出后缀（仅 produces_file 且 overwrite=false）"},
            },
            "required": ["path", "processor_type"],
        },
        requires_confirmation=True,
        handler=_processors_run,
    ),
}


def get_tool(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)


def openai_tools() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for spec in TOOLS.values():
        out.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        })
    return out


def tool_result_to_content(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except TypeError:
        return json.dumps({"result": str(result)}, ensure_ascii=False)

