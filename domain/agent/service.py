import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from domain.ai import AIProviderService, MissingModelError, chat_completion, chat_completion_stream
from domain.auth import User

from .mcp import mcp_client_session, mcp_content_to_text
from .tools import tool_result_to_content
from .types import AgentChatRequest, PendingMcpCall


def _normalize_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    value = str(path).strip().replace("\\", "/")
    if not value:
        return None
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/") or "/"


def _build_system_prompt(current_path: Optional[str]) -> str:
    lines = [
        "你是 Foxel 的 AI 助手。",
        "你可以通过 MCP 工具对文件/目录进行查询、读写、移动、复制、删除，以及运行处理器（processor）。",
        "",
        "可用工具：",
        "- time：获取服务器当前时间（精确到秒，英文星期），支持 year/month/day/hour/minute/second 偏移。",
        "- web_fetch：抓取网页（HTTP 请求），支持 GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS，返回状态/标题/正文/链接等。",
        "- vfs_list_dir：浏览目录（列出 entries + pagination）。",
        "- vfs_stat：查看文件/目录信息。",
        "- vfs_read_text：读取文本文件内容（不支持二进制）。",
        "- vfs_search：搜索文件（vector/filename）。",
        "- vfs_write_text：写入文本文件内容（覆盖）。",
        "- vfs_mkdir：创建目录。",
        "- vfs_delete：删除文件或目录。",
        "- vfs_move：移动路径。",
        "- vfs_copy：复制路径。",
        "- vfs_rename：重命名路径。",
        "- processors_list：获取可用处理器列表（含 type/name/config_schema/produces_file/supports_directory）。",
        "- processors_run：运行处理器处理文件或目录（会返回 task_id 或 task_ids）。",
        "",
        "规则：",
        "1) 读操作（web_fetch/vfs_list_dir/vfs_stat/vfs_read_text/vfs_search）可直接调用工具。",
        "2) 写/改/删操作（vfs_write_text/vfs_mkdir/vfs_delete/vfs_move/vfs_copy/vfs_rename/processors_run）默认需要用户确认；只有在开启自动执行时才应直接执行。",
        "3) 用户未给出明确路径时先追问；若提供了“当前文件管理目录”，可以基于它把相对描述补全为绝对路径（以 / 开头）。",
        "4) 修改文件内容：先读取（vfs_read_text）→给出改动点→确认后再写入（vfs_write_text）。",
        "5) processors_run 返回任务 id 后，说明任务已提交，可在任务队列查看进度。",
        "6) 回答语言跟随用户；用户用英文则用英文，用户用中文则用中文。回答尽量简洁。",
    ]
    if current_path:
        lines.append("")
        lines.append(f"当前文件管理目录：{current_path}")
    return "\n".join(lines)


def _ensure_mcp_call_ids(message: Dict[str, Any]) -> Dict[str, Any]:
    mcp_calls = message.get("mcp_calls")
    if not isinstance(mcp_calls, list):
        return message

    changed = False
    for idx, call in enumerate(mcp_calls):
        if not isinstance(call, dict):
            continue
        call_id = call.get("id")
        if isinstance(call_id, str) and call_id.strip():
            continue
        call["id"] = f"call_{idx}"
        changed = True

    if changed:
        message["mcp_calls"] = mcp_calls
    return message


def _extract_pending(mcp_call: Dict[str, Any], requires_confirmation: bool) -> PendingMcpCall:
    arguments = mcp_call.get("arguments") if isinstance(mcp_call.get("arguments"), dict) else {}
    return PendingMcpCall(
        id=str(mcp_call.get("id") or ""),
        name=str(mcp_call.get("name") or ""),
        arguments=arguments,
        requires_confirmation=requires_confirmation,
    )


def _find_last_assistant_mcp_calls(messages: List[Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        mcp_calls = msg.get("mcp_calls")
        if isinstance(mcp_calls, list) and mcp_calls:
            return idx, msg
    raise HTTPException(status_code=400, detail="没有可确认的待执行操作")


def _existing_mcp_result_ids(messages: List[Dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        call_id = msg.get("mcp_call_id")
        if isinstance(call_id, str) and call_id.strip():
            ids.add(call_id)
    return ids


def _tool_requires_confirmation(tool_descriptor: Dict[str, Any]) -> bool:
    meta = tool_descriptor.get("meta") if isinstance(tool_descriptor.get("meta"), dict) else {}
    if "requires_confirmation" in meta:
        return bool(meta.get("requires_confirmation"))
    annotations = tool_descriptor.get("annotations") if isinstance(tool_descriptor.get("annotations"), dict) else {}
    return not bool(annotations.get("readOnlyHint"))


async def _choose_chat_ability() -> str:
    tools_model = await AIProviderService.get_default_model("tools")
    return "tools" if tools_model else "chat"


def _sse(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _format_exc(exc: BaseException) -> str:
    text = str(exc)
    return text if text else exc.__class__.__name__


async def _list_mcp_tools(session) -> List[Dict[str, Any]]:
    result = await session.list_tools()
    tools: List[Dict[str, Any]] = []
    for item in result.tools:
        annotations = getattr(item, "annotations", None)
        meta = getattr(item, "meta", None)
        tools.append(
            {
                "name": str(getattr(item, "name", "") or ""),
                "description": str(getattr(item, "description", "") or ""),
                "input_schema": getattr(item, "inputSchema", None) or {},
                "annotations": annotations.model_dump(exclude_none=True) if annotations is not None else {},
                "meta": meta if isinstance(meta, dict) else {},
            }
        )
    return tools


async def _execute_mcp_call(session, name: str, arguments: Dict[str, Any]) -> str:
    result = await session.call_tool(name, arguments)
    return mcp_content_to_text(result.content, result.structuredContent)


class AgentService:
    @classmethod
    async def chat(cls, req: AgentChatRequest, user: Optional[User]) -> Dict[str, Any]:
        history: List[Dict[str, Any]] = list(req.messages or [])
        current_path = _normalize_path(req.context.current_path if req.context else None)
        system_prompt = _build_system_prompt(current_path)
        internal_messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}] + history
        new_messages: List[Dict[str, Any]] = []
        pending: List[PendingMcpCall] = []

        approved_ids = {i for i in (req.approved_mcp_call_ids or []) if isinstance(i, str) and i.strip()}
        rejected_ids = {i for i in (req.rejected_mcp_call_ids or []) if isinstance(i, str) and i.strip()}

        async with mcp_client_session(user, current_path) as mcp_session:
            tools_schema = await _list_mcp_tools(mcp_session)
            tool_index = {tool["name"]: tool for tool in tools_schema if tool.get("name")}

            if approved_ids or rejected_ids:
                _, last_call_msg = _find_last_assistant_mcp_calls(internal_messages)
                last_call_msg = _ensure_mcp_call_ids(last_call_msg)
                mcp_calls = last_call_msg.get("mcp_calls") or []
                call_map: Dict[str, Dict[str, Any]] = {
                    str(call.get("id")): call
                    for call in mcp_calls
                    if isinstance(call, dict) and isinstance(call.get("id"), str)
                }

                existing_ids = _existing_mcp_result_ids(internal_messages)
                for call_id in approved_ids | rejected_ids:
                    if call_id in existing_ids:
                        continue
                    mcp_call = call_map.get(call_id)
                    if not mcp_call:
                        continue
                    name = str(mcp_call.get("name") or "")
                    arguments = mcp_call.get("arguments") if isinstance(mcp_call.get("arguments"), dict) else {}
                    tool_desc = tool_index.get(name)

                    if call_id in rejected_ids:
                        content = tool_result_to_content({"canceled": True, "reason": "user_rejected"})
                    elif not tool_desc:
                        content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                    else:
                        try:
                            content = await _execute_mcp_call(mcp_session, name, arguments)
                        except Exception as exc:  # noqa: BLE001
                            content = tool_result_to_content({"error": str(exc)})
                    tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                    internal_messages.append(tool_msg)
                    new_messages.append(tool_msg)

            ability = await _choose_chat_ability()

            for _ in range(8):
                try:
                    assistant = await chat_completion(
                        internal_messages,
                        ability=ability,
                        tools=tools_schema,
                        tool_choice="auto",
                        timeout=60.0,
                    )
                except MissingModelError as exc:
                    raise HTTPException(status_code=400, detail=_format_exc(exc)) from exc
                except httpx.HTTPStatusError as exc:
                    raise HTTPException(status_code=502, detail=f"对话请求失败: {_format_exc(exc)}") from exc
                except httpx.RequestError as exc:
                    raise HTTPException(status_code=502, detail=f"对话请求异常: {_format_exc(exc)}") from exc

                assistant = _ensure_mcp_call_ids(assistant if isinstance(assistant, dict) else {"role": "assistant", "content": ""})
                internal_messages.append(assistant)
                new_messages.append(assistant)

                mcp_calls = assistant.get("mcp_calls")
                if not isinstance(mcp_calls, list) or not mcp_calls:
                    break

                pending = []
                for call in mcp_calls:
                    if not isinstance(call, dict):
                        continue
                    call_id = str(call.get("id") or "")
                    name = str(call.get("name") or "")
                    arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                    tool_desc = tool_index.get(name)

                    if not tool_desc:
                        content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                        tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                        internal_messages.append(tool_msg)
                        new_messages.append(tool_msg)
                        continue

                    if _tool_requires_confirmation(tool_desc) and not req.auto_execute:
                        pending.append(_extract_pending(call, True))
                        continue

                    try:
                        content = await _execute_mcp_call(mcp_session, name, arguments)
                    except Exception as exc:  # noqa: BLE001
                        content = tool_result_to_content({"error": str(exc)})
                    tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                    internal_messages.append(tool_msg)
                    new_messages.append(tool_msg)

                if pending:
                    break

        payload: Dict[str, Any] = {"messages": new_messages}
        if pending:
            payload["pending_mcp_calls"] = [item.model_dump() for item in pending]
        return payload

    @classmethod
    async def chat_stream(cls, req: AgentChatRequest, user: Optional[User]):
        history: List[Dict[str, Any]] = list(req.messages or [])
        current_path = _normalize_path(req.context.current_path if req.context else None)
        system_prompt = _build_system_prompt(current_path)
        internal_messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}] + history
        new_messages: List[Dict[str, Any]] = []
        pending: List[PendingMcpCall] = []

        approved_ids = {i for i in (req.approved_mcp_call_ids or []) if isinstance(i, str) and i.strip()}
        rejected_ids = {i for i in (req.rejected_mcp_call_ids or []) if isinstance(i, str) and i.strip()}

        try:
            async with mcp_client_session(user, current_path) as mcp_session:
                tools_schema = await _list_mcp_tools(mcp_session)
                tool_index = {tool["name"]: tool for tool in tools_schema if tool.get("name")}

                if approved_ids or rejected_ids:
                    _, last_call_msg = _find_last_assistant_mcp_calls(internal_messages)
                    last_call_msg = _ensure_mcp_call_ids(last_call_msg)
                    mcp_calls = last_call_msg.get("mcp_calls") or []
                    call_map: Dict[str, Dict[str, Any]] = {
                        str(call.get("id")): call
                        for call in mcp_calls
                        if isinstance(call, dict) and isinstance(call.get("id"), str)
                    }

                    existing_ids = _existing_mcp_result_ids(internal_messages)
                    for call_id in approved_ids | rejected_ids:
                        if call_id in existing_ids:
                            continue
                        mcp_call = call_map.get(call_id)
                        if not mcp_call:
                            continue

                        name = str(mcp_call.get("name") or "")
                        arguments = mcp_call.get("arguments") if isinstance(mcp_call.get("arguments"), dict) else {}
                        tool_desc = tool_index.get(name)

                        if call_id in rejected_ids:
                            content = tool_result_to_content({"canceled": True, "reason": "user_rejected"})
                            tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                            internal_messages.append(tool_msg)
                            new_messages.append(tool_msg)
                            yield _sse("mcp_call_end", {"mcp_call_id": call_id, "name": name, "message": tool_msg})
                            continue

                        if not tool_desc:
                            content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                            tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                            internal_messages.append(tool_msg)
                            new_messages.append(tool_msg)
                            yield _sse("mcp_call_end", {"mcp_call_id": call_id, "name": name, "message": tool_msg})
                            continue

                        yield _sse("mcp_call_start", {"mcp_call_id": call_id, "name": name})
                        try:
                            content = await _execute_mcp_call(mcp_session, name, arguments)
                        except Exception as exc:  # noqa: BLE001
                            content = tool_result_to_content({"error": str(exc)})
                        tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                        internal_messages.append(tool_msg)
                        new_messages.append(tool_msg)
                        yield _sse("mcp_call_end", {"mcp_call_id": call_id, "name": name, "message": tool_msg})

                ability = await _choose_chat_ability()

                for _ in range(8):
                    assistant_event_id = str(uuid.uuid4())
                    yield _sse("assistant_start", {"id": assistant_event_id})

                    assistant_message: Dict[str, Any] | None = None
                    try:
                        async for event in chat_completion_stream(
                            internal_messages,
                            ability=ability,
                            tools=tools_schema,
                            tool_choice="auto",
                            timeout=60.0,
                        ):
                            event_type = event.get("type")
                            if event_type == "delta":
                                delta = event.get("delta")
                                if isinstance(delta, str) and delta:
                                    yield _sse("assistant_delta", {"id": assistant_event_id, "delta": delta})
                            elif event_type == "message":
                                msg = event.get("message")
                                if isinstance(msg, dict):
                                    assistant_message = msg
                    except MissingModelError as exc:
                        raise HTTPException(status_code=400, detail=_format_exc(exc)) from exc
                    except httpx.HTTPStatusError as exc:
                        raise HTTPException(status_code=502, detail=f"对话请求失败: {_format_exc(exc)}") from exc
                    except httpx.RequestError as exc:
                        raise HTTPException(status_code=502, detail=f"对话请求异常: {_format_exc(exc)}") from exc

                    if not assistant_message:
                        assistant_message = {"role": "assistant", "content": ""}

                    assistant_message = _ensure_mcp_call_ids(assistant_message)
                    internal_messages.append(assistant_message)
                    new_messages.append(assistant_message)
                    yield _sse("assistant_end", {"id": assistant_event_id, "message": assistant_message})

                    mcp_calls = assistant_message.get("mcp_calls")
                    if not isinstance(mcp_calls, list) or not mcp_calls:
                        break

                    pending = []
                    for call in mcp_calls:
                        if not isinstance(call, dict):
                            continue
                        call_id = str(call.get("id") or "")
                        name = str(call.get("name") or "")
                        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                        tool_desc = tool_index.get(name)

                        if not tool_desc:
                            content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                            tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                            internal_messages.append(tool_msg)
                            new_messages.append(tool_msg)
                            yield _sse("mcp_call_end", {"mcp_call_id": call_id, "name": name, "message": tool_msg})
                            continue

                        if _tool_requires_confirmation(tool_desc) and not req.auto_execute:
                            pending.append(_extract_pending(call, True))
                            continue

                        yield _sse("mcp_call_start", {"mcp_call_id": call_id, "name": name})
                        try:
                            content = await _execute_mcp_call(mcp_session, name, arguments)
                        except Exception as exc:  # noqa: BLE001
                            content = tool_result_to_content({"error": str(exc)})
                        tool_msg = {"role": "tool", "mcp_call_id": call_id, "content": content}
                        internal_messages.append(tool_msg)
                        new_messages.append(tool_msg)
                        yield _sse("mcp_call_end", {"mcp_call_id": call_id, "name": name, "message": tool_msg})

                    if pending:
                        yield _sse("pending", {"pending_mcp_calls": [item.model_dump() for item in pending]})
                        break

            payload: Dict[str, Any] = {"messages": new_messages}
            if pending:
                payload["pending_mcp_calls"] = [item.model_dump() for item in pending]
            yield _sse("done", payload)

        except asyncio.CancelledError:
            return
        except HTTPException as exc:
            detail = exc.detail
            content = detail if isinstance(detail, str) else str(detail)
            if not content.strip():
                content = f"请求失败({exc.status_code})"
            new_messages.append({"role": "assistant", "content": content})
            payload: Dict[str, Any] = {"messages": new_messages}
            if pending:
                payload["pending_mcp_calls"] = [item.model_dump() for item in pending]
            yield _sse("done", payload)
        except Exception as exc:  # noqa: BLE001
            new_messages.append({"role": "assistant", "content": f"服务端异常: {_format_exc(exc)}"})
            payload: Dict[str, Any] = {"messages": new_messages}
            if pending:
                payload["pending_mcp_calls"] = [item.model_dump() for item in pending]
            yield _sse("done", payload)
