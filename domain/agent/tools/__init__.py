from typing import Any, Dict, List, Optional

from .base import ToolSpec, tool_result_to_content
from .processors import TOOLS as PROCESSOR_TOOLS
from .time import TOOLS as TIME_TOOLS
from .vfs import TOOLS as VFS_TOOLS
from .web_fetch import TOOLS as WEB_FETCH_TOOLS

TOOLS: Dict[str, ToolSpec] = {}
for group in (TIME_TOOLS, WEB_FETCH_TOOLS, PROCESSOR_TOOLS, VFS_TOOLS):
    TOOLS.update(group)


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


__all__ = [
    "ToolSpec",
    "get_tool",
    "openai_tools",
    "tool_result_to_content",
]
