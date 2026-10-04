from typing import Any, Dict, Optional

from domain.virtual_fs import VirtualFSService
from domain.virtual_fs.search import VirtualFSSearchService

from .base import ToolSpec, tool_error
from domain.permission.execution import current_user_id, require_path, require_paths
from domain.permission.types import PathAction


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
    path = await require_path(path, PathAction.READ)
    page = int(args.get("page") or 1)
    page_size = int(args.get("page_size") or 50)
    sort_by = str(args.get("sort_by") or "name")
    sort_order = str(args.get("sort_order") or "asc")
    return await VirtualFSService.list_directory_with_permission(
        path, current_user_id(), page, page_size, sort_by, sort_order, args.get("cursor")
    )


async def _vfs_stat(args: Dict[str, Any]) -> Any:
    path = _require_vfs_path(args.get("path"), "path")
    path = await require_path(path, PathAction.READ)
    return await VirtualFSService.stat(path)


async def _vfs_read_text(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _require_vfs_path(args.get("path"), "path")
    path = await require_path(path, PathAction.READ)
    encoding = str(args.get("encoding") or "utf-8")
    max_chars = int(args.get("max_chars") or 8000)

    data = await VirtualFSService.read_file(path)
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode(encoding)
        except UnicodeDecodeError:
            return tool_error("unsupported_capability", "binary_or_invalid_text")
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
    path = await require_path(path, PathAction.WRITE)
    encoding = str(args.get("encoding") or "utf-8")
    content = str(args.get("content") or "")
    data = content.encode(encoding)
    await VirtualFSService.write_file(path, data)
    return {"written": True, "path": path, "encoding": encoding, "bytes": len(data)}


async def _vfs_mkdir(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _require_vfs_path(args.get("path"), "path")
    path = await require_path(path, PathAction.WRITE)
    return await VirtualFSService.mkdir(path)


async def _vfs_delete(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _require_vfs_path(args.get("path"), "path")
    path = await require_path(path, PathAction.DELETE)
    return await VirtualFSService.delete(path)


async def _vfs_move(args: Dict[str, Any]) -> Dict[str, Any]:
    src = _require_vfs_path(args.get("src"), "src")
    dst = _require_vfs_path(args.get("dst"), "dst")
    if src == "/" or dst == "/":
        raise ValueError("invalid_path")
    await require_paths([(src, PathAction.READ), (src, PathAction.DELETE), (dst, PathAction.WRITE)])
    overwrite = bool(args.get("overwrite") or False)
    return await VirtualFSService.move(src, dst, overwrite)


async def _vfs_copy(args: Dict[str, Any]) -> Dict[str, Any]:
    src = _require_vfs_path(args.get("src"), "src")
    dst = _require_vfs_path(args.get("dst"), "dst")
    if src == "/" or dst == "/":
        raise ValueError("invalid_path")
    await require_paths([(src, PathAction.READ), (dst, PathAction.WRITE)])
    overwrite = bool(args.get("overwrite") or False)
    return await VirtualFSService.copy(src, dst, overwrite)


async def _vfs_rename(args: Dict[str, Any]) -> Dict[str, Any]:
    src = _require_vfs_path(args.get("src"), "src")
    dst = _require_vfs_path(args.get("dst"), "dst")
    if src == "/" or dst == "/":
        raise ValueError("invalid_path")
    await require_paths([(src, PathAction.READ), (src, PathAction.DELETE), (dst, PathAction.WRITE)])
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
    result = await VirtualFSSearchService.search(q, top_k, mode, page, page_size)
    from domain.permission.service import PermissionService
    allowed = await PermissionService.filter_paths_by_permission(
        current_user_id(), [str(item.path) for item in result.get("items", [])], PathAction.READ
    )
    allowed_set = set(allowed)
    result["items"] = [item for item in result.get("items", []) if str(item.path) in allowed_set]
    return result


TOOLS: Dict[str, ToolSpec] = {
    "vfs_list_dir": ToolSpec(
        name="vfs_list_dir",
        description=(
            "Use to browse a known directory, understand its structure, or find files within it. Returns entries and pagination."
            " Start at / to discover accessible roots. Lists one level only; call again to explore subdirectories."
            " Follow pagination to retrieve more entries. Use vfs_search first when the file location is unknown."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute Foxel virtual directory path, e.g. / or /photos; not a server-local path."},
                "page": {"type": "integer", "minimum": 1, "description": "Page number starting at 1. Default: 1. Increment for page-based pagination."},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Entries per page. Default: 50. Maximum: 100."},
                "sort_by": {"type": "string", "enum": ["name", "size", "mtime"], "description": "Sort by name, size, or modification time (mtime). Default: name."},
                "sort_order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort direction. Default: asc. Use mtime with desc for recently modified files."},
                "cursor": {"type": "string", "description": "For cursor pagination, pass the previous response's next_cursor unchanged. Keep path, sorting, and page_size the same."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_list_dir,
    ),
    "vfs_stat": ToolSpec(
        name="vfs_stat",
        description=(
            "Use to check whether a path exists, distinguish files from directories, or inspect size and modification time."
            " Returns metadata such as size, mtime, and is_dir; extra fields depend on the storage adapter."
            " Verify a target before reading, writing, or running a processor. Use vfs_read_text for text content."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute Foxel virtual file or directory path, e.g. /docs/report.txt."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_stat,
    ),
    "vfs_read_text": ToolSpec(
        name="vfs_read_text",
        description=(
            "Use to read, summarize, or inspect text files such as Markdown, configuration, or source code before editing."
            " Returns content, truncated, and the original character count (length). Defaults to the first 8000 characters."
            " When truncated=true, content is incomplete; increase max_chars and reread, up to 100000. Does not support paged reads."
            " Decoding failures return an error; specify encoding when known. Not suitable for images or other binary files."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute Foxel virtual text file path, e.g. /docs/report.md."},
                "encoding": {"type": "string", "description": "Text encoding. Default: utf-8."},
                "max_chars": {"type": "integer", "minimum": 1, "maximum": 100000, "description": "Maximum characters returned from the start of the file. Default: 8000. Limit: 100000. Increase and reread if truncated."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_read_text,
    ),
    "vfs_write_text": ToolSpec(
        name="vfs_write_text",
        description=(
            "Use to create a text file or save its complete edited contents. Replaces an existing file in full."
            " Before editing an existing file, read it with vfs_read_text and check truncated to avoid overwriting it with incomplete content."
            " content must contain the complete final text; an empty string clears the file. Does not append or perform partial replacements."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute Foxel virtual text file path, e.g. /docs/report.md."},
                "content": {"type": "string", "description": "Complete final text replacing any existing contents. An empty string clears the file."},
                "encoding": {"type": "string", "description": "Text encoding. Default: utf-8."},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_write_text,
    ),
    "vfs_mkdir": ToolSpec(
        name="vfs_mkdir",
        description=(
            "Use to create a Foxel virtual directory for organizing files or preparing an output location."
            " path is the complete new directory path. Handling of missing parents and existing directories depends on the storage adapter."
            " Check the target and parent with vfs_stat or vfs_list_dir first if needed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full absolute Foxel virtual directory path to create, e.g. /docs/archive."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_mkdir,
    ),
    "vfs_delete": ToolSpec(
        name="vfs_delete",
        description=(
            "Use when the user requests removal of a file or directory. Directory deletion may remove contents recursively, depending on the storage adapter."
            " Verify the full path before calling; inspect the deletion scope with vfs_stat and vfs_list_dir if needed."
            " Does not guarantee a recycle bin or recovery. Cannot delete the virtual root /."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute Foxel virtual path to delete, e.g. /docs/archive or /docs/old.txt."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_delete,
    ),
    "vfs_move": ToolSpec(
        name="vfs_move",
        description=(
            "Use to relocate a file or directory, reorganize folders, or transfer between storage mounts."
            " src and dst are full paths; dst must include the final file or directory name. The source is removed after successful completion."
            " Does not overwrite by default. overwrite=true may replace the destination and its directory contents."
            " queued=true with task_id means the operation was queued, not completed. Confirm completion in the Foxel task queue before reporting success."
        ),
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Absolute Foxel virtual source path."},
                "dst": {"type": "string", "description": "Full absolute destination path including the final file or directory name, e.g. /archive/report.md."},
                "overwrite": {"type": "boolean", "description": "Default: false. true allows replacing an existing destination, potentially including all contents of a destination directory."},
            },
            "required": ["src", "dst"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_move,
    ),
    "vfs_copy": ToolSpec(
        name="vfs_copy",
        description=(
            "Use to create a copy or backup, including across storage mounts, while preserving the source file or directory."
            " dst is the full destination path including the final file or directory name."
            " Does not overwrite by default. overwrite=true may replace the destination and its directory contents."
            " queued=true with task_id means the operation was queued, not completed. Confirm completion in the Foxel task queue before reporting success."
        ),
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Absolute Foxel virtual source path."},
                "dst": {"type": "string", "description": "Full absolute copy destination including the final file or directory name, e.g. /backup/report.md."},
                "overwrite": {"type": "boolean", "description": "Default: false. true allows replacing an existing destination, potentially including all contents of a destination directory."},
            },
            "required": ["src", "dst"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_copy,
    ),
    "vfs_rename": ToolSpec(
        name="vfs_rename",
        description=(
            "Use to change a file or directory name; keep src and dst in the same parent directory when renaming."
            " dst is the full path including the new name. Does not overwrite an existing destination by default."
            " Only supports renaming within one storage mount. Use vfs_move for relocation or transfers across mounts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Absolute Foxel virtual source path."},
                "dst": {"type": "string", "description": "Full absolute path including the new name, e.g. rename /docs/old.md to /docs/new.md."},
                "overwrite": {"type": "boolean", "description": "Default: false. true allows replacing an existing destination, potentially including all contents of a destination directory."},
            },
            "required": ["src", "dst"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_vfs_rename,
    ),
    "vfs_search": ToolSpec(
        name="vfs_search",
        description=(
            "Use to find files by topic or name when their location is unknown. Returns only matches the current user can read."
            " Default vector mode supports natural-language semantic queries and requires an embedding model and content vector index."
            " filename mode matches filename or path keywords and supports page/page_size pagination."
            " Both modes depend on existing indexes; empty results do not prove a file is absent. Browse known directories with vfs_list_dir."
            " Verify returned paths with vfs_stat or vfs_read_text. Search snippets are not complete file contents."
        ),
        parameters={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Nonempty query. For vector mode, describe content naturally, e.g. beach photos from last year's trip. For filename mode, use filename or path keywords, e.g. report.pdf."},
                "mode": {"type": "string", "enum": ["vector", "filename"], "description": "vector for semantic content search (default), filename for filename or path keyword search. Both require existing indexes."},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Maximum results in vector mode. Default: 10. Limit: 100."},
                "page": {"type": "integer", "minimum": 1, "description": "Page number in filename mode. Default: 1."},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Results per page in filename mode. Default: 10. Limit: 100."},
            },
            "required": ["q"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_vfs_search,
    ),
}
