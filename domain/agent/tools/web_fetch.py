from html.parser import HTMLParser
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx

from .base import ToolSpec
from domain.permission.execution import ExecutionError


class _HtmlTextExtractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []
        self._link_set: set[str] = set()
        self._title_parts: List[str] = []
        self._text_parts: List[str] = []
        self._in_title = False
        self._skip_text = False

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in ("script", "style", "noscript"):
            self._skip_text = True
        if tag != "a":
            return
        href = ""
        for key, value in attrs:
            if key.lower() == "href":
                href = str(value or "").strip()
                break
        if not href or href.startswith("#"):
            return
        lower = href.lower()
        if lower.startswith(("javascript:", "mailto:", "tel:", "data:")):
            return
        resolved = urljoin(self.base_url, href)
        if resolved in self._link_set:
            return
        self._link_set.add(resolved)
        self.links.append(resolved)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style", "noscript"):
            self._skip_text = False

    def handle_data(self, data: str):
        if not data:
            return
        if self._in_title:
            self._title_parts.append(data)
        if self._skip_text:
            return
        if data.strip():
            self._text_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(part.strip() for part in self._title_parts if part and part.strip()).strip()

    @property
    def text(self) -> str:
        if not self._text_parts:
            return ""
        text = " ".join(part.strip() for part in self._text_parts if part and part.strip())
        return " ".join(text.split())


async def _web_fetch(args: Dict[str, Any]) -> Dict[str, Any]:
    url = str(args.get("url") or "").strip()
    if not url:
        raise ValueError("missing_url")

    method = str(args.get("method") or "GET").upper()
    allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    if method not in allowed_methods:
        raise ValueError("invalid_method")

    headers_raw = args.get("headers")
    headers = {str(k): str(v) for k, v in headers_raw.items() if v is not None} if isinstance(headers_raw, dict) else None
    params_raw = args.get("params")
    params = {str(k): str(v) for k, v in params_raw.items() if v is not None} if isinstance(params_raw, dict) else None
    json_body = args.get("json") if "json" in args else None
    body = args.get("body")

    request_kwargs: Dict[str, Any] = {}
    if headers:
        request_kwargs["headers"] = headers
    if params:
        request_kwargs["params"] = params
    if json_body is not None:
        request_kwargs["json"] = json_body
    elif body is not None:
        request_kwargs["content"] = str(body)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        async with client.stream(method, url, **request_kwargs) as resp:
            chunks = []
            size = 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    raise ExecutionError("response_too_large")
                chunks.append(chunk)
            await resp.aclose()
            body_bytes = b"".join(chunks)

    content_type = resp.headers.get("content-type") or ""
    text = body_bytes.decode(resp.encoding or "utf-8", errors="replace")
    is_html = "html" in content_type.lower()
    if not is_html:
        probe = text.lstrip()[:200].lower()
        if "<html" in probe or "<!doctype html" in probe:
            is_html = True

    html = ""
    title = ""
    links: List[str] = []
    extracted_text = text

    if is_html and text:
        html = text
        parser = _HtmlTextExtractor(str(resp.url))
        parser.feed(text)
        title = parser.title
        links = parser.links
        extracted_text = parser.text

    data = {
        "url": url,
        "method": method,
        "final_url": str(resp.url),
        "status_code": resp.status_code,
        "content_type": content_type,
        "title": title,
        "html": html,
        "text": extracted_text,
        "links": links,
    }

    summary_parts = [method, str(resp.status_code)]
    if title:
        summary_parts.append(title)
    summary_parts.append(f"{len(links)} links")
    summary = " · ".join(summary_parts)

    view = {
        "type": "text",
        "text": extracted_text,
        "meta": {
            "url": url,
            "final_url": str(resp.url),
            "status_code": resp.status_code,
            "content_type": content_type,
            "title": title,
            "method": method,
            "links": len(links),
        },
    }
    return {"ok": True, "summary": summary, "view": view, "data": data}


TOOLS: Dict[str, ToolSpec] = {
    "web_fetch": ToolSpec(
        name="web_fetch",
        description=(
            "Use to read a known webpage URL, extract text and links, or call an HTTP API. Defaults to GET and follows redirects."
            " HTML responses include title/text/html/links; other responses include decoded text."
            " Check status_code to determine HTTP success; content_type and final_url are also returned."
            " Does not execute JavaScript, render browser-dependent content, or search the web."
            " Supports GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS without tool approval; write methods may change external systems."
            " HTTP timeout: 20 seconds. Response body limit: 2 MiB; larger responses return an error."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full http:// or https:// URL, e.g. https://example.com/article. Must not be search keywords."},
                "method": {"type": "string", "description": "HTTP method: GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS. Default: GET. All methods bypass tool approval."},
                "headers": {"type": "object", "description": "Request headers with string values, e.g. Accept or Content-Type, as required by the target API.", "additionalProperties": {"type": "string"}},
                "params": {"type": "object", "description": "URL query parameters with string values, e.g. {\"page\": \"1\"}.", "additionalProperties": {"type": "string"}},
                "json": {"type": "object", "description": "JSON object request body. Takes precedence when body is also provided."},
                "body": {"type": "string", "description": "Raw text request body, used only when json is omitted. Set Content-Type in headers if needed."},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_web_fetch,
    ),
}
