from typing import Any, Dict, Optional

from domain.virtual_fs import VirtualFSService
from domain.virtual_fs.search import VirtualFSSearchService

from .base import ToolSpec


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
