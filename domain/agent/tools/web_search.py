import uuid
from typing import Any, Dict, List, Optional

import httpx

from .base import ToolSpec
from domain.config import ConfigService
from domain.permission.execution import ExecutionError

SEARCH_MCP_URL = "https://search.parallel.ai/mcp"
SEARCH_ENABLED_KEY = "AGENT_WEB_SEARCH_ENABLED"
SEARCH_TOOL_NAME = "web_search"
SEARCH_TIMEOUT_SECONDS = 20.0
SEARCH_MAX_QUERIES = 5
SEARCH_MAX_RESULTS = 20


async def search_enabled() -> bool:
    """Whether an administrator left web search on; the tool is hidden otherwise."""
    value = str(await ConfigService.get(SEARCH_ENABLED_KEY, "1")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _tool_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    return result.get("structuredContent") or result


def _plain_text(payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    for item in payload.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(parts)


def _jsonrpc_failure(payload: Dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "search_failed")
    return "search_failed"


def _parse_body(response: httpx.Response) -> Optional[Dict[str, Any]]:
    """Read a JSON-RPC payload from a plain JSON or an SSE response body."""
    text = response.text
    if not text:
        return None
    try:
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        pass
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        candidate = line[len("data:"):].strip()
        if not candidate or candidate == "[DONE]":
            continue
        try:
            parsed = httpx.Response(200, content=candidate).json()
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


class _SearchSession:
    """One MCP session against the Parallel search endpoint, closed when the tool returns."""

    session_id = uuid.uuid4().hex

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._protocol_version = "2025-06-18"
        self._next_id = 0

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": self.session_id,
            "MCP-Protocol-Version": self._protocol_version,
        }
        return headers

    async def __aenter__(self) -> "_SearchSession":
        self._client = httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True)
        await self._request("initialize", {
            "protocolVersion": self._protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "foxel", "version": "1"},
        })
        await self._notify("notifications/initialized", {})
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _rpc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _post(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self._client is None:
            raise ExecutionError("execution_failed")
        response = await self._client.post(SEARCH_MCP_URL, headers=self._headers(), json=payload)
        if response.status_code >= 400:
            raise ExecutionError("search_failed")
        return _parse_body(response)

    async def _request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = await self._post({"jsonrpc": "2.0", "id": self._rpc_id(), "method": method, "params": params})
        if payload is None:
            return None
        error = payload.get("error")
        if error:
            raise ExecutionError("search_failed")
        return payload.get("result") if isinstance(payload.get("result"), dict) else payload

    async def _notify(self, method: str, params: Dict[str, Any]) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params})

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        if result is None:
            raise ExecutionError("search_failed")
        return result


def _collect_results(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    collected: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        excerpts = [_clean_excerpt(value) for value in item.get("excerpts") or [] if isinstance(value, str)]
        collected.append({
            "url": url,
            "title": str(item.get("title") or "").strip(),
            "publish_date": item.get("publish_date"),
            "excerpts": [value for value in excerpts if value],
        })
    return collected


def _clean_excerpt(value: str) -> str:
    """Drop an optional markdown fence wrapper that the host may add around an excerpt."""
    text = value.strip()
    if text.startswith("```"):
        body = text.split("\n", 1)
        if len(body) == 2:
            text = body[1].rsplit("```", 1)[0].strip()
    return text


async def _web_search(args: Dict[str, Any]) -> Dict[str, Any]:
    if not await search_enabled():
        raise ExecutionError("unsupported_capability")

    query_raw = args.get("query")
    queries = [value.strip() for value in query_raw if value.strip()] if isinstance(query_raw, list) else []
    if not queries:
        raise ValueError("missing_query")
    if len(queries) > SEARCH_MAX_QUERIES:
        raise ExecutionError("invalid_arguments")

    objective = str(args.get("objective") or "").strip() or queries[0]
    count = args.get("count", SEARCH_MAX_RESULTS)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1 or count > SEARCH_MAX_RESULTS:
        raise ExecutionError("invalid_arguments")

    arguments = {
        "objective": objective,
        "search_queries": queries,
        "session_id": _SearchSession.session_id,
    }
    if args.get("model"):
        arguments["model_name"] = str(args["model"])

    async with _SearchSession() as session:
        payload = await session.call_tool("web_search", arguments)

    if payload.get("isError"):
        raise ExecutionError("search_failed")

    data = _tool_payload(payload)
    results = _collect_results(data)[:count]
    if not results:
        text = _plain_text(payload).strip()
        if text and _jsonrpc_failure(payload):
            raise ExecutionError("search_failed")
        return {
            "ok": True,
            "summary": f"{len(queries)} queries · 0 results",
            "view": {"type": "text", "text": "No results.", "meta": {"queries": len(queries), "results": 0}},
            "data": {"query": queries, "objective": objective, "results": [], "session_id": _SearchSession.session_id},
        }

    lines: List[str] = []
    for position, item in enumerate(results, start=1):
        heading = item["title"] or item["url"]
        lines.append(f"{position}. {heading}")
        lines.append(item["url"])
        for excerpt in item["excerpts"][:2]:
            lines.append(excerpt)
        lines.append("")

    return {
        "ok": True,
        "summary": f"{len(queries)} queries · {len(results)} results",
        "view": {
            "type": "text",
            "text": "\n".join(lines).strip(),
            "meta": {"queries": len(queries), "results": len(results), "objective": objective},
        },
        "data": {
            "query": queries,
            "objective": objective,
            "results": results,
            "session_id": _SearchSession.session_id,
        },
    }


TOOLS: Dict[str, ToolSpec] = {
    "web_search": ToolSpec(
        name="web_search",
        description=(
            "Use to find current web sources when the URL is unknown. Returns each result's URL, title, publish date and excerpts."
            " Search queries are short keywords, three to six words each; use site:<domain> to stay on one site."
            " Excerpts answer most questions directly, so only follow up with web_fetch for a particular page, exact wording or full text."
            " Read-only, needs no approval, and does not open pages itself."
            " HTTP timeout: 20 seconds. An administrator can disable search in the system settings."
        ),
        parameters={
            "type": "object",
            "properties": {
                "objective": {"type": "string", "description": "What the search should find, in one sentence, e.g. the value or fact you need. Defaults to the first query."},
                "query": {
                    "type": "array",
                    "description": "One to five keyword queries, three to six words each, e.g. [\"opentofu 1.12 release notes\"]. Use site:<domain> to restrict a query to one site.",
                    "items": {"type": "string"},
                },
                "count": {"type": "integer", "description": "Maximum results to return, 1 to 20. Default: 20."},
                "model": {"type": "string", "description": "Identifier of the model calling this tool, e.g. gpt-5.5. Product analytics only."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_web_search,
    ),
}
