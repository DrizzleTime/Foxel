import calendar
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from domain.processors import ProcessDirectoryRequest, ProcessRequest, ProcessorService
from domain.virtual_fs import VirtualFSService
from domain.virtual_fs.search import VirtualFSSearchService


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    requires_confirmation: bool
    handler: Callable[[Dict[str, Any]], Awaitable[Any]]


def _parse_offset(args: Dict[str, Any], key: str) -> int:
    value = args.get(key)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _add_months(dt: datetime, months: int) -> datetime:
    if months == 0:
        return dt
    total = dt.year * 12 + (dt.month - 1) + months
    year = total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


async def _time(args: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now()
    year_offset = _parse_offset(args, "year")
    month_offset = _parse_offset(args, "month")
    day_offset = _parse_offset(args, "day")
    hour_offset = _parse_offset(args, "hour")
    minute_offset = _parse_offset(args, "minute")
    second_offset = _parse_offset(args, "second")

    dt = _add_months(now, year_offset * 12 + month_offset)
    dt = dt + timedelta(days=day_offset, hours=hour_offset, minutes=minute_offset, seconds=second_offset)

    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    weekday = weekday_names[dt.weekday()]
    dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "ok": True,
        "summary": f"{dt_str} · {weekday}",
        "data": {
            "datetime": dt_str,
            "weekday": weekday,
            "offset": {
                "year": year_offset,
                "month": month_offset,
                "day": day_offset,
                "hour": hour_offset,
                "minute": minute_offset,
                "second": second_offset,
            },
        },
    }


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


def _normalize_vfs_path(value: Any) -> str:
    s = str(value or "").strip().replace("\\", "/")
    if not s:
        return ""
    if not s.startswith("/"):
        s = "/" + s
    s = s.rstrip("/") or "/"
    return s


def _require_vfs_path(value: Any, field: str) -> str:
    path = _normalize_vfs_path(value)
    if not path:
        raise ValueError(f"missing_{field}")
    return path


async def _vfs_list_dir(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _normalize_vfs_path(args.get("path") or "/") or "/"
    page = int(args.get("page") or 1)
    page_size = int(args.get("page_size") or 50)
    sort_by = str(args.get("sort_by") or "name")
    sort_order = str(args.get("sort_order") or "asc")
    return await VirtualFSService.list_directory(path, page, page_size, sort_by, sort_order)


async def _vfs_stat(args: Dict[str, Any]) -> Any:
    path = _require_vfs_path(args.get("path"), "path")
    return await VirtualFSService.stat(path)


async def _vfs_read_text(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _require_vfs_path(args.get("path"), "path")
    encoding = str(args.get("encoding") or "utf-8")
    max_chars = int(args.get("max_chars") or 8000)

    data = await VirtualFSService.read_file(path)
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode(encoding)
        except UnicodeDecodeError:
            return {"error": "binary_or_invalid_text", "path": path}
    elif isinstance(data, str):
        text = data
    else:
        text = str(data)

    original_len = len(text)
    truncated = original_len > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "path": path,
        "encoding": encoding,
        "content": text,
        "truncated": truncated,
        "length": original_len,
    }


async def _vfs_write_text(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _require_vfs_path(args.get("path"), "path")
    if path == "/":
        raise ValueError("invalid_path")
    encoding = str(args.get("encoding") or "utf-8")
    content = str(args.get("content") or "")
    data = content.encode(encoding)
    await VirtualFSService.write_file(path, data)
    return {"written": True, "path": path, "encoding": encoding, "bytes": len(data)}


async def _vfs_mkdir(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _require_vfs_path(args.get("path"), "path")
    return await VirtualFSService.mkdir(path)


async def _vfs_delete(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _require_vfs_path(args.get("path"), "path")
    return await VirtualFSService.delete(path)


async def _vfs_move(args: Dict[str, Any]) -> Dict[str, Any]:
    src = _require_vfs_path(args.get("src"), "src")
    dst = _require_vfs_path(args.get("dst"), "dst")
    if src == "/" or dst == "/":
        raise ValueError("invalid_path")
    overwrite = bool(args.get("overwrite") or False)
    return await VirtualFSService.move(src, dst, overwrite)


async def _vfs_copy(args: Dict[str, Any]) -> Dict[str, Any]:
    src = _require_vfs_path(args.get("src"), "src")
    dst = _require_vfs_path(args.get("dst"), "dst")
    if src == "/" or dst == "/":
        raise ValueError("invalid_path")
    overwrite = bool(args.get("overwrite") or False)
    return await VirtualFSService.copy(src, dst, overwrite)


async def _vfs_rename(args: Dict[str, Any]) -> Dict[str, Any]:
    src = _require_vfs_path(args.get("src"), "src")
    dst = _require_vfs_path(args.get("dst"), "dst")
    if src == "/" or dst == "/":
        raise ValueError("invalid_path")
    overwrite = bool(args.get("overwrite") or False)
    return await VirtualFSService.rename(src, dst, overwrite)


async def _vfs_search(args: Dict[str, Any]) -> Dict[str, Any]:
    q = str(args.get("q") or "").strip()
    if not q:
        raise ValueError("missing_q")
    mode = str(args.get("mode") or "vector")
    top_k = int(args.get("top_k") or 10)
    page = int(args.get("page") or 1)
    page_size = int(args.get("page_size") or 10)
    return await VirtualFSSearchService.search(q, top_k, mode, page, page_size)


TOOLS: Dict[str, ToolSpec] = {
    "time": ToolSpec(
        name="time",
        description=(
            "获取服务器当前时间（精确到秒，含英文星期）。"
            " 支持 year/month/day/hour/minute/second 偏移（可为负数）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年偏移（可为负数）"},
                "month": {"type": "integer", "description": "月偏移（可为负数）"},
                "day": {"type": "integer", "description": "日偏移（可为负数）"},
                "hour": {"type": "integer", "description": "时偏移（可为负数）"},
                "minute": {"type": "integer", "description": "分偏移（可为负数）"},
                "second": {"type": "integer", "description": "秒偏移（可为负数）"},
            },
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_time,
    ),
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
    "vfs_list_dir": ToolSpec(
        name="vfs_list_dir",
        description="浏览目录（列出 entries + pagination）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径（绝对路径，如 /foo/bar）"},
                "page": {"type": "integer", "description": "页码（从 1 开始）"},
                "page_size": {"type": "integer", "description": "每页条数"},
                "sort_by": {"type": "string", "description": "排序字段：name/size/mtime"},
                "sort_order": {"type": "string", "description": "排序顺序：asc/desc"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_list_dir,
    ),
    "vfs_stat": ToolSpec(
        name="vfs_stat",
        description="查看文件/目录信息（size/mtime/is_dir/has_thumbnail/vector_index 等）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "路径（绝对路径，如 /foo/bar.txt）"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_stat,
    ),
    "vfs_read_text": ToolSpec(
        name="vfs_read_text",
        description="读取文本文件内容（解码失败视为二进制，返回 error）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（绝对路径，如 /foo/bar.md）"},
                "encoding": {"type": "string", "description": "文本编码（默认 utf-8）"},
                "max_chars": {"type": "integer", "description": "最多返回的字符数（默认 8000）"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_read_text,
    ),
    "vfs_write_text": ToolSpec(
        name="vfs_write_text",
        description="写入文本文件内容（会覆盖目标文件）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（绝对路径，如 /foo/bar.md）"},
                "content": {"type": "string", "description": "要写入的文本内容"},
                "encoding": {"type": "string", "description": "文本编码（默认 utf-8）"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_write_text,
    ),
    "vfs_mkdir": ToolSpec(
        name="vfs_mkdir",
        description="创建目录。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径（绝对路径，如 /foo/bar）"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_mkdir,
    ),
    "vfs_delete": ToolSpec(
        name="vfs_delete",
        description="删除文件或目录（由底层适配器决定是否递归）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "路径（绝对路径，如 /foo/bar 或 /foo/bar.txt）"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_delete,
    ),
    "vfs_move": ToolSpec(
        name="vfs_move",
        description="移动路径（可能进入任务队列）。",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源路径（绝对路径）"},
                "dst": {"type": "string", "description": "目标路径（绝对路径）"},
                "overwrite": {"type": "boolean", "description": "是否允许覆盖已存在目标（默认 false）"},
            },
            "required": ["src", "dst"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_move,
    ),
    "vfs_copy": ToolSpec(
        name="vfs_copy",
        description="复制路径（可能进入任务队列）。",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源路径（绝对路径）"},
                "dst": {"type": "string", "description": "目标路径（绝对路径）"},
                "overwrite": {"type": "boolean", "description": "是否覆盖已存在目标（默认 false）"},
            },
            "required": ["src", "dst"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_copy,
    ),
    "vfs_rename": ToolSpec(
        name="vfs_rename",
        description="重命名路径（本质是同目录 move）。",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源路径（绝对路径）"},
                "dst": {"type": "string", "description": "目标路径（绝对路径）"},
                "overwrite": {"type": "boolean", "description": "是否允许覆盖已存在目标（默认 false）"},
            },
            "required": ["src", "dst"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_rename,
    ),
    "vfs_search": ToolSpec(
        name="vfs_search",
        description="搜索文件（mode=vector 或 filename）。",
        parameters={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "搜索关键词"},
                "mode": {"type": "string", "description": "搜索模式：vector/filename（默认 vector）"},
                "top_k": {"type": "integer", "description": "返回数量（vector 模式使用，默认 10）"},
                "page": {"type": "integer", "description": "页码（filename 模式使用，默认 1）"},
                "page_size": {"type": "integer", "description": "分页大小（filename 模式使用，默认 10）"},
            },
            "required": ["q"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_search,
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


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _list_to_view_items(items: List[Any]) -> List[Any]:
    normalized: List[Any] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append({str(k): _stringify_value(v) for k, v in item.items()})
        else:
            normalized.append(_stringify_value(item))
    return normalized


def _dict_to_kv_items(data: Dict[str, Any]) -> List[Dict[str, str]]:
    return [{"key": str(k), "value": _stringify_value(v)} for k, v in data.items()]


def _first_list_field(data: Dict[str, Any]) -> tuple[Optional[str], Optional[List[Any]]]:
    for key, value in data.items():
        if isinstance(value, list):
            return str(key), value
    return None, None


def _build_view(data: Any) -> Dict[str, Any]:
    if data is None:
        return {"type": "kv", "items": []}
    if isinstance(data, str):
        return {"type": "text", "text": data}
    if isinstance(data, list):
        return {"type": "list", "items": _list_to_view_items(data)}
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, str):
            meta = {k: _stringify_value(v) for k, v in data.items() if k != "content"}
            view: Dict[str, Any] = {"type": "text", "text": content}
            if meta:
                view["meta"] = meta
            return view
        list_key, list_val = _first_list_field(data)
        if list_key and isinstance(list_val, list):
            meta = {k: _stringify_value(v) for k, v in data.items() if k != list_key}
            view = {"type": "list", "title": list_key, "items": _list_to_view_items(list_val)}
            if meta:
                view["meta"] = meta
            return view
        return {"type": "kv", "items": _dict_to_kv_items(data)}
    return {"type": "text", "text": _stringify_value(data)}


def _build_summary(view: Dict[str, Any]) -> str:
    view_type = str(view.get("type") or "")
    if view_type == "text":
        text = view.get("text")
        size = len(text) if isinstance(text, str) else 0
        return f"chars: {size}" if size else "text"
    if view_type == "list":
        items = view.get("items")
        count = len(items) if isinstance(items, list) else 0
        title = str(view.get("title") or "items")
        return f"{title}: {count}"
    if view_type == "kv":
        items = view.get("items")
        count = len(items) if isinstance(items, list) else 0
        return f"fields: {count}"
    if view_type == "error":
        return str(view.get("message") or "error")
    return ""


def _build_error_payload(code: str, message: str, detail: Any = None) -> Dict[str, Any]:
    summary = "Canceled" if code == "canceled" else message or "error"
    view = {"type": "error", "message": summary}
    payload: Dict[str, Any] = {
        "ok": False,
        "summary": summary,
        "view": view,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if detail is not None:
        payload["error"]["detail"] = detail
    return payload


def _normalize_tool_result(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict) and "ok" in result:
        payload = dict(result)
        if payload.get("ok") is False:
            error = payload.get("error")
            message = _stringify_value(error.get("message") if isinstance(error, dict) else error)
            payload.setdefault("summary", message or "error")
            payload.setdefault("view", {"type": "error", "message": payload["summary"]})
            return payload
        data = payload.get("data")
        if payload.get("view") is None:
            payload["view"] = _build_view(data)
        if not payload.get("summary"):
            payload["summary"] = _build_summary(payload["view"])
        return payload

    if isinstance(result, dict) and result.get("canceled"):
        reason = _stringify_value(result.get("reason") or "canceled")
        return _build_error_payload("canceled", reason, detail=result)

    if isinstance(result, dict) and "error" in result:
        error = result.get("error")
        message = _stringify_value(error.get("message") if isinstance(error, dict) else error)
        return _build_error_payload("error", message, detail=error)

    view = _build_view(result)
    summary = _build_summary(view)
    return {"ok": True, "summary": summary, "view": view, "data": result}


def tool_result_to_content(result: Any) -> str:
    payload = _normalize_tool_result(result)
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps({"ok": False, "summary": "error", "view": {"type": "error", "message": "error"}}, ensure_ascii=False)
