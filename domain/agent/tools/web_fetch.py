from html.parser import HTMLParser
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx

from .base import ToolSpec


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
        resp = await client.request(method, url, **request_kwargs)

    content_type = resp.headers.get("content-type") or ""
    text = resp.text or ""
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
            "抓取网页内容，返回状态、标题、正文、HTML、链接等信息。"
            " 支持 GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL"},
                "method": {"type": "string", "description": "请求方法（默认 GET）"},
                "headers": {"type": "object", "description": "请求头", "additionalProperties": {"type": "string"}},
                "params": {"type": "object", "description": "查询参数", "additionalProperties": {"type": "string"}},
                "json": {"type": "object", "description": "JSON 请求体"},
                "body": {"type": "string", "description": "原始请求体"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_web_fetch,
    ),
}
