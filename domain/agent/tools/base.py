import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    requires_confirmation: bool
    handler: Callable[[Dict[str, Any]], Awaitable[Any]]


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
