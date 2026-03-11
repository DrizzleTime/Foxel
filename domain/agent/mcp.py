import inspect
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated, Any, Literal
from urllib.parse import quote, unquote

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.server import AuthSettings
from mcp.types import ToolAnnotations
from pydantic import Field

from domain.auth import AuthService, User
from domain.processors import ProcessorService

from .tools import get_tool, mcp_tool_descriptors
from .tools.base import McpToolDescriptor, normalize_tool_result, tool_result_to_content

INTERNAL_MCP_BASE_URL = "http://127.0.0.1:8000/"
CURRENT_PATH_HEADER = "x-foxel-current-path"


def _normalize_path(path: str | None) -> str | None:
    if not path:
        return None
    value = str(path).strip().replace("\\", "/")
    if not value:
        return None
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/") or "/"


def _header_current_path(ctx: Context | None) -> str | None:
    request = ctx.request_context.request if ctx and ctx.request_context else None
    if request is None:
        return None
    return _normalize_path(request.headers.get(CURRENT_PATH_HEADER))


def _field_annotation(schema: dict[str, Any], required: bool) -> tuple[Any, Any]:
    raw_type = schema.get("type")
    enum_values = schema.get("enum")
    description = str(schema.get("description") or "").strip() or None
    default = schema.get("default", inspect.Parameter.empty if required else None)

    annotation: Any
    if isinstance(enum_values, list) and enum_values:
        annotation = Literal.__getitem__(tuple(enum_values))
    elif raw_type == "string":
        annotation = str
    elif raw_type == "integer":
        annotation = int
    elif raw_type == "number":
        annotation = float
    elif raw_type == "boolean":
        annotation = bool
    elif raw_type == "array":
        annotation = list[Any]
    elif raw_type == "object":
        annotation = dict[str, Any]
    else:
        annotation = Any

    if not required and default is None:
        annotation = annotation | None

    if description:
        annotation = Annotated[annotation, Field(description=description)]
    return annotation, default


def _build_tool_signature(descriptor: McpToolDescriptor) -> inspect.Signature:
    schema = descriptor.input_schema if isinstance(descriptor.input_schema, dict) else {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = set(schema.get("required") or [])
    parameters: list[inspect.Parameter] = []
    for key, value in properties.items():
        prop_schema = value if isinstance(value, dict) else {}
        annotation, default = _field_annotation(prop_schema, key in required)
        parameters.append(
            inspect.Parameter(
                str(key),
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=annotation,
            )
        )
    return inspect.Signature(parameters=parameters, return_annotation=dict[str, Any])


def _build_tool_wrapper(descriptor: McpToolDescriptor):
    async def wrapper(**kwargs: Any) -> dict[str, Any]:
        spec = get_tool(descriptor.name)
        if not spec:
            return normalize_tool_result({"error": f"unknown_tool: {descriptor.name}"})
        try:
            result = await spec.handler(kwargs)
            return normalize_tool_result(result)
        except Exception as exc:  # noqa: BLE001
            return normalize_tool_result({"error": str(exc)})

    wrapper.__name__ = descriptor.name
    wrapper.__doc__ = descriptor.description
    wrapper.__signature__ = _build_tool_signature(descriptor)
    return wrapper


class FoxelMcpTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user = await AuthService.get_current_active_user(await AuthService.get_current_user(token))
        except Exception:  # noqa: BLE001
            return None
        return AccessToken(token=token, client_id=user.username, scopes=[])


MCP_SERVER = FastMCP(
    name="Foxel MCP",
    instructions="Foxel 内置 MCP 服务，提供文件系统、网页抓取、时间与处理器相关能力。",
    streamable_http_path="/",
    token_verifier=FoxelMcpTokenVerifier(),
    auth=AuthSettings(
        issuer_url="http://127.0.0.1:8000",
        resource_server_url=None,
        required_scopes=[],
    ),
)


for descriptor in mcp_tool_descriptors():
    MCP_SERVER.add_tool(
        _build_tool_wrapper(descriptor),
        name=descriptor.name,
        description=descriptor.description,
        annotations=ToolAnnotations.model_validate(descriptor.annotations),
        meta=descriptor.meta,
        structured_output=False,
    )


@MCP_SERVER.resource(
    "foxel://context/current-path",
    name="current_path",
    title="Current Path",
    description="返回当前请求上下文里的文件管理目录。",
    mime_type="application/json",
)
def current_path_resource() -> dict[str, Any]:
    return {"current_path": None}


@MCP_SERVER.resource(
    "foxel://policy/tool-confirmation",
    name="tool_confirmation_policy",
    title="Tool Confirmation Policy",
    description="返回 Foxel agent 对工具审批的策略。",
    mime_type="application/json",
)
def tool_confirmation_policy_resource() -> dict[str, Any]:
    return {
        "read_tools": [tool.name for tool in mcp_tool_descriptors() if not tool.requires_confirmation],
        "write_tools": [tool.name for tool in mcp_tool_descriptors() if tool.requires_confirmation],
        "rule": "直接调用 MCP tool 时不额外审批；通过 agent 代表用户执行写操作时需要审批。",
    }


@MCP_SERVER.resource(
    "foxel://processors/index",
    name="processors_index",
    title="Processors Index",
    description="返回当前可用处理器列表。",
    mime_type="application/json",
)
def processors_index_resource() -> dict[str, Any]:
    return {"processors": ProcessorService.list_processors()}


async def _tool_resource(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = get_tool(tool_name)
    if not spec:
        return normalize_tool_result({"error": f"unknown_tool: {tool_name}"})
    try:
        result = await spec.handler(arguments)
        return normalize_tool_result(result)
    except Exception as exc:  # noqa: BLE001
        return normalize_tool_result({"error": str(exc)})


@MCP_SERVER.resource(
    "foxel://vfs/stat/{path}",
    name="vfs_stat_resource",
    title="VFS Stat",
    description="读取指定路径的文件或目录元信息；path 需要 URL 编码。",
    mime_type="application/json",
)
async def vfs_stat_resource(path: str) -> dict[str, Any]:
    return await _tool_resource("vfs_stat", {"path": "/" + unquote(path).lstrip("/")})


@MCP_SERVER.resource(
    "foxel://vfs/text/{path}",
    name="vfs_text_resource",
    title="VFS Text",
    description="读取文本文件内容；path 需要 URL 编码。",
    mime_type="application/json",
)
async def vfs_text_resource(path: str) -> dict[str, Any]:
    return await _tool_resource("vfs_read_text", {"path": "/" + unquote(path).lstrip("/")})


@MCP_SERVER.resource(
    "foxel://vfs/dir/{path}",
    name="vfs_dir_resource",
    title="VFS Directory",
    description="列出目录内容；path 需要 URL 编码。",
    mime_type="application/json",
)
async def vfs_dir_resource(path: str) -> dict[str, Any]:
    return await _tool_resource("vfs_list_dir", {"path": "/" + unquote(path).lstrip("/")})


@MCP_SERVER.resource(
    "foxel://vfs/search/{query}",
    name="vfs_search_resource",
    title="VFS Search",
    description="搜索文件；query 需要 URL 编码。",
    mime_type="application/json",
)
async def vfs_search_resource(query: str) -> dict[str, Any]:
    return await _tool_resource("vfs_search", {"q": unquote(query)})


@MCP_SERVER.prompt(name="browse_path", title="Browse Path", description="生成浏览目录的推荐提示词。")
def browse_path_prompt(path: Annotated[str, Field(description="目标目录路径")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"请先浏览目录 `{path}`，总结结构与关键文件。必要时调用 vfs_list_dir 与 vfs_stat。"}]


@MCP_SERVER.prompt(name="inspect_file", title="Inspect File", description="生成查看文件的推荐提示词。")
def inspect_file_prompt(path: Annotated[str, Field(description="目标文件路径")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"请检查文件 `{path}` 的内容与用途。必要时调用 vfs_read_text。"}]


@MCP_SERVER.prompt(name="search_files", title="Search Files", description="生成搜索文件的推荐提示词。")
def search_files_prompt(query: Annotated[str, Field(description="搜索关键词")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"请搜索与 `{query}` 相关的文件，并按相关性总结。必要时调用 vfs_search。"}]


@MCP_SERVER.prompt(name="edit_file_safely", title="Edit File Safely", description="生成安全修改文件的推荐提示词。")
def edit_file_safely_prompt(path: Annotated[str, Field(description="目标文件路径")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"请先读取 `{path}`，解释拟修改点，再等待我确认后执行写入。"}]


@MCP_SERVER.prompt(name="run_processor", title="Run Processor", description="生成运行处理器的推荐提示词。")
def run_processor_prompt(
    path: Annotated[str, Field(description="目标文件或目录路径")],
    processor_type: Annotated[str, Field(description="处理器类型")],
) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"请检查 `{path}` 是否适合运行处理器 `{processor_type}`，确认参数后再执行 processors_run。"}]


@MCP_SERVER.prompt(name="fetch_web_page", title="Fetch Web Page", description="生成抓取网页的推荐提示词。")
def fetch_web_page_prompt(url: Annotated[str, Field(description="目标网址")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"请抓取网页 `{url}`，并总结标题、正文与关键链接。必要时调用 web_fetch。"}]


MCP_HTTP_APP = MCP_SERVER.streamable_http_app()


def loopback_httpx_client_factory(app):
    def factory(headers: dict[str, str] | None = None, timeout=None, auth=None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=INTERNAL_MCP_BASE_URL.rstrip("/"),
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=True,
        )

    return factory


async def create_loopback_mcp_headers(user: User | None, current_path: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if user is not None:
        token = await AuthService.create_access_token(
            {"sub": user.username},
            expires_delta=timedelta(minutes=5),
        )
        headers["Authorization"] = f"Bearer {token}"
    if current_path:
        headers[CURRENT_PATH_HEADER] = current_path
    return headers


@asynccontextmanager
async def mcp_client_session(user: User | None, current_path: str | None = None):
    headers = await create_loopback_mcp_headers(user, current_path)
    async with streamablehttp_client(
        INTERNAL_MCP_BASE_URL,
        headers=headers,
        httpx_client_factory=loopback_httpx_client_factory(MCP_HTTP_APP),
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


def mcp_content_to_text(content: list[Any], structured_content: dict[str, Any] | None = None) -> str:
    if structured_content is not None:
        try:
            return json.dumps(structured_content, ensure_ascii=False)
        except TypeError:
            pass

    text_parts: list[str] = []
    for item in content:
        item_type = getattr(item, "type", None)
        if item_type == "text":
            text = getattr(item, "text", None)
            if isinstance(text, str) and text:
                text_parts.append(text)
    if text_parts:
        return "\n".join(text_parts)
    return tool_result_to_content({"error": "empty_mcp_content"})


def encode_resource_path(path: str) -> str:
    return quote(path.lstrip("/"), safe="")
