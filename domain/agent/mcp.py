import inspect
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import timedelta
from typing import Annotated, Any, Literal
from urllib.parse import quote, unquote, urlsplit

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from domain.auth import AuthService, User
from domain.config import ConfigService
from domain.processors import ProcessorService

from .tools import mcp_tool_descriptors
from .tools.base import McpToolDescriptor, tool_result_to_content
from .current_path import (
    CURRENT_PATH_HEADER,
    decode_current_path,
    encode_current_path,
    ensure_ascii_header_value,
)
from .execution import execute_tool
from domain.permission.execution import ExecutionError, normalize_path

INTERNAL_MCP_BASE_URL = "http://127.0.0.1:8000/"
_resource_context: ContextVar[Context | None] = ContextVar("foxel_resource_context", default=None)


class FoxelMCPServer(MCPServer):
    async def read_resource(self, uri, context=None):
        # The SDK does not inject Context into fixed-URI resource handlers.
        token = _resource_context.set(context)
        try:
            return await super().read_resource(uri, context)
        finally:
            _resource_context.reset(token)


def _normalize_path(path: str | None) -> str | None:
    if not path:
        return None
    value = str(path).strip().replace("\\", "/")
    if not value:
        return None
    if not value.startswith("/"):
        value = "/" + value
    return normalize_path(value)


def _header_current_path(ctx: Context | None) -> str | None:
    request = ctx.request_context.request if ctx and ctx.request_context else None
    if request is None:
        return None
    try:
        return _normalize_path(decode_current_path(request.headers.get(CURRENT_PATH_HEADER)))
    except ExecutionError:
        return None


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

    if enum_values:
        annotation = Annotated[annotation, Field(description=description)]
    elif raw_type in {"string", "integer", "number", "boolean"}:
        annotation = Annotated[annotation, Field(
            description=description, strict=True,
            ge=schema.get("minimum") if raw_type in {"integer", "number"} else None,
            le=schema.get("maximum") if raw_type in {"integer", "number"} else None,
        )]
    elif description:
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
    async def wrapper(ctx: Context, **kwargs: Any) -> dict[str, Any]:
        return await _tool_resource(descriptor.name, kwargs, _header_current_path(ctx))

    wrapper.__name__ = descriptor.name
    wrapper.__doc__ = descriptor.description
    wrapper.__signature__ = _build_tool_signature(descriptor)
    return wrapper


async def _authenticated_user() -> User | None:
    token = get_access_token()
    if token is None:
        return None
    try:
        return await AuthService.get_current_active_user(await AuthService.get_current_user(token.token))
    except Exception:
        return None


class FoxelMcpTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user = await AuthService.get_current_active_user(await AuthService.get_current_user(token))
        except Exception:  # noqa: BLE001
            return None
        return AccessToken(token=token, client_id=user.username, scopes=[])


MCP_SERVER = FoxelMCPServer(
    name="Foxel MCP",
    instructions=(
        "Foxel MCP provides private-cloud file browsing, search, text reading and writing, file organization, and processor tasks."
        " All file paths are absolute paths in the Foxel virtual filesystem (e.g. /photos/a.jpg), not server-local paths."
        " File operations enforce the authenticated account's path permissions."
        " Use vfs_list_dir for known directories, vfs_search for unknown file locations, vfs_stat for metadata, and vfs_read_text for text."
        " Read existing text and verify that it is complete before editing. Choose vfs_copy to preserve the source or vfs_move to relocate it."
        " Before running a processor, use processors_list to discover available types, supported formats, and configuration."
        " Tool results include ok; inspect error on failure. A task_id or queued=true indicates submission, not completion."
        " Check progress in the Foxel task queue; this service does not provide a task-status tool."
        " External MCP clients handle confirmation for file mutations. The built-in agent uses its own tool approval policy."
    ),
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
    description="Read when the user refers to the current directory. Returns the Foxel path from x-foxel-current-path, or null if no valid path was supplied. The header value must be ASCII: percent-encode the UTF-8 path and prefix it with 'foxel-cp1:'. Values without that prefix are read as raw paths for backward compatibility.",
    mime_type="application/json",
)
def current_path_resource() -> dict[str, Any]:
    return {"current_path": _header_current_path(_resource_context.get())}


@MCP_SERVER.resource(
    "foxel://policy/tool-confirmation",
    name="tool_confirmation_policy",
    title="Tool Confirmation Policy",
    description="Read to understand confirmation policies for exposed tools. Lists read-only, unconfirmed, and confirmation-required tools, and distinguishes client confirmation from built-in agent approval.",
    mime_type="application/json",
)
def tool_confirmation_policy_resource() -> dict[str, Any]:
    return {
        "read_tools": [tool.name for tool in mcp_tool_descriptors() if tool.annotations.get("readOnlyHint")],
        "unconfirmed_tools": [tool.name for tool in mcp_tool_descriptors() if not tool.requires_confirmation],
        "write_tools": [tool.name for tool in mcp_tool_descriptors() if tool.requires_confirmation],
        "rule": "Direct MCP calls do not require additional server approval; external clients handle confirmation. The built-in agent requires approval for confirmation-required tools unless auto-execution is enabled.",
    }


@MCP_SERVER.resource(
    "foxel://processors/index",
    name="processors_index",
    title="Processors Index",
    description="Read to choose a processor and check supported formats and configuration schemas. Returns the same available processor list as processors_list.",
    mime_type="application/json",
)
def processors_index_resource() -> dict[str, Any]:
    return {"processors": ProcessorService.list_processors()}


async def _tool_resource(tool_name: str, arguments: dict[str, Any], current_path: str | None = None) -> dict[str, Any]:
    return await execute_tool(tool_name, arguments, await _authenticated_user(), current_path)


@MCP_SERVER.resource(
    "foxel://vfs/stat/{path}",
    name="vfs_stat_resource",
    title="VFS Stat",
    description="Read to inspect file or directory type, size, and modification time. URL-encode the Foxel path without its leading /. Uses the same permission checks as vfs_stat.",
    mime_type="application/json",
)
async def vfs_stat_resource(path: str, ctx: Context) -> dict[str, Any]:
    return await _tool_resource("vfs_stat", {"path": "/" + unquote(path).lstrip("/")}, _header_current_path(ctx))


@MCP_SERVER.resource(
    "foxel://vfs/text/{path}",
    name="vfs_text_resource",
    title="VFS Text",
    description="Read a known text file. URL-encode the Foxel path without its leading /. Defaults to UTF-8 and up to 8000 characters; use vfs_read_text to adjust encoding or length.",
    mime_type="application/json",
)
async def vfs_text_resource(path: str, ctx: Context) -> dict[str, Any]:
    return await _tool_resource("vfs_read_text", {"path": "/" + unquote(path).lstrip("/")}, _header_current_path(ctx))


@MCP_SERVER.resource(
    "foxel://vfs/dir/{path}",
    name="vfs_dir_resource",
    title="VFS Directory",
    description="Read the first page of a known directory. URL-encode the Foxel path without its leading /. Use vfs_list_dir for pagination or sorting.",
    mime_type="application/json",
)
async def vfs_dir_resource(path: str, ctx: Context) -> dict[str, Any]:
    return await _tool_resource("vfs_list_dir", {"path": "/" + unquote(path).lstrip("/")}, _header_current_path(ctx))


@MCP_SERVER.resource(
    "foxel://vfs/search/{query}",
    name="vfs_search_resource",
    title="VFS Search",
    description="Read to run default semantic search using a natural-language content description. URL-encode query. Requires a content vector index; use vfs_search for filename search or custom limits.",
    mime_type="application/json",
)
async def vfs_search_resource(query: str, ctx: Context) -> dict[str, Any]:
    return await _tool_resource("vfs_search", {"q": unquote(query)}, _header_current_path(ctx))


@MCP_SERVER.prompt(name="browse_path", title="Browse Path", description="Use to explore an unfamiliar directory and summarize its structure with vfs_list_dir and vfs_stat.")
def browse_path_prompt(path: Annotated[str, Field(description="Absolute Foxel directory path to explore.")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"Browse directory `{path}` and summarize its structure and key files. Use vfs_list_dir and vfs_stat as needed."}]


@MCP_SERVER.prompt(name="inspect_file", title="Inspect File", description="Use to read a known text file and explain its contents and purpose with vfs_read_text.")
def inspect_file_prompt(path: Annotated[str, Field(description="Absolute Foxel text file path to inspect.")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"Inspect the contents and purpose of file `{path}`. Use vfs_read_text as needed and check whether the content is truncated."}]


@MCP_SERVER.prompt(name="search_files", title="Search Files", description="Use to find and summarize relevant files with vfs_search when their locations are unknown.")
def search_files_prompt(query: Annotated[str, Field(description="Content description or filename keywords to search for.")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"Search for files related to `{query}` and summarize them by relevance. Use vfs_search with the appropriate search mode."}]


@MCP_SERVER.prompt(name="edit_file_safely", title="Edit File Safely", description="Use to review an edit plan before replacing existing text: read first, explain changes, and wait for confirmation before writing.")
def edit_file_safely_prompt(path: Annotated[str, Field(description="Absolute Foxel text file path to edit.")]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"Read `{path}` and verify that the content is complete. Explain the proposed edits, then wait for my confirmation before writing."}]


@MCP_SERVER.prompt(name="run_processor", title="Run Processor", description="Use with a known input path and processor type to check compatibility and confirm settings before submitting a processing task.")
def run_processor_prompt(
    path: Annotated[str, Field(description="Absolute Foxel file or directory path to process.")],
    processor_type: Annotated[str, Field(description="Processor type from processors_list.")],
) -> list[dict[str, Any]]:
    return [{"role": "user", "content": f"Check processors_list and verify that `{path}` is suitable for processor `{processor_type}`. Confirm settings before calling processors_run. A task_id indicates submission, not completion."}]


_LOOPBACK_HOSTS = ["127.0.0.1", "localhost", "[::1]"]
MCP_TRANSPORT_SECURITY = TransportSecuritySettings(
    allowed_hosts=[value for host in _LOOPBACK_HOSTS for value in (host, f"{host}:*")],
    allowed_origins=[value for host in _LOOPBACK_HOSTS for value in (f"http://{host}", f"http://{host}:*")],
)
MCP_HTTP_APP = MCP_SERVER.streamable_http_app(
    streamable_http_path="/", transport_security=MCP_TRANSPORT_SECURITY,
)


def _configure_mcp_domain(domain: str | None) -> None:
    hosts = [value for host in _LOOPBACK_HOSTS for value in (host, f"{host}:*")]
    origins = [value for host in _LOOPBACK_HOSTS for value in (f"http://{host}", f"http://{host}:*")]
    try:
        url = urlsplit((domain or "").strip())
        if url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password:
            port = url.port
            host = url.netloc.lower()
            hosts.append(host)
            origins.append(f"{url.scheme}://{host}")
            if port == {"http": 80, "https": 443}[url.scheme]:
                hosts.append(host.rsplit(":", 1)[0])
                origins.append(f"{url.scheme}://{hosts[-1]}")
    except ValueError:
        pass
    # Existing SDK sessions share this policy, so domain changes apply immediately.
    MCP_TRANSPORT_SECURITY.allowed_hosts = hosts
    MCP_TRANSPORT_SECURITY.allowed_origins = origins


class RemoteMcpApp:
    """Gate external access while keeping the agent's loopback transport available."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            enabled = str(await ConfigService.get("MCP_ENABLED", "1")).strip().lower()
            if enabled not in {"1", "true", "yes", "on"}:
                response = JSONResponse({"detail": "Remote MCP is disabled"}, status_code=503)
                await response(scope, receive, send)
                return
            _configure_mcp_domain(await ConfigService.get("APP_DOMAIN"))
        await self.app(scope, receive, send)


MCP_REMOTE_APP = RemoteMcpApp(MCP_HTTP_APP)


async def create_loopback_mcp_headers(user: User | None, current_path: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if user is not None:
        token = await AuthService.create_access_token(
            {"sub": user.username},
            expires_delta=timedelta(minutes=5),
        )
        headers["Authorization"] = f"Bearer {token}"
    if current_path:
        headers[CURRENT_PATH_HEADER] = ensure_ascii_header_value(
            CURRENT_PATH_HEADER, encode_current_path(current_path)
        )
    return headers


@asynccontextmanager
async def mcp_client_session(user: User | None, current_path: str | None = None):
    headers = await create_loopback_mcp_headers(user, current_path)
    timeout = httpx2.Timeout(30.0, read=300.0)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=MCP_HTTP_APP),
        base_url=INTERNAL_MCP_BASE_URL.rstrip("/"),
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    ) as http_client:
        transport = streamable_http_client(
            INTERNAL_MCP_BASE_URL,
            http_client=http_client,
        )
        async with Client(transport, mode="2026-07-28") as client:
            yield client


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
