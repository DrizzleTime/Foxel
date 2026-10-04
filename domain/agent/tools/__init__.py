from typing import Any, Dict, List, Optional

from .base import McpToolDescriptor, ToolSpec, tool_result_to_content, tool_spec_to_mcp_descriptor
from .processors import TOOLS as PROCESSOR_TOOLS
from .time import TOOLS as TIME_TOOLS
from .vfs import TOOLS as VFS_TOOLS
from .web_fetch import TOOLS as WEB_FETCH_TOOLS

TOOLS: Dict[str, ToolSpec] = {}
for group in (TIME_TOOLS, WEB_FETCH_TOOLS, PROCESSOR_TOOLS, VFS_TOOLS):
    TOOLS.update(group)

AGENT_ONLY_TOOL_NAMES = frozenset({"time", "web_fetch"})


def get_tool(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)


def list_tool_specs() -> List[ToolSpec]:
    return list(TOOLS.values())


def mcp_tool_descriptors(*, include_agent_only: bool = False) -> List[McpToolDescriptor]:
    return [
        tool_spec_to_mcp_descriptor(spec) for spec in TOOLS.values()
        if include_agent_only or spec.name not in AGENT_ONLY_TOOL_NAMES
    ]


__all__ = [
    "AGENT_ONLY_TOOL_NAMES",
    "McpToolDescriptor",
    "ToolSpec",
    "get_tool",
    "list_tool_specs",
    "mcp_tool_descriptors",
    "tool_result_to_content",
]
