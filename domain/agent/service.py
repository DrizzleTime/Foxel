import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from domain.ai import AIProviderService, MissingModelError, chat_completion, chat_completion_stream
from domain.auth import User
from .tools import get_tool, openai_tools, tool_result_to_content
from .types import AgentChatRequest, PendingToolCall


def _normalize_path(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    s = str(p).strip()
    if not s:
        return None
    s = s.replace("\\", "/")
    if not s.startswith("/"):
        s = "/" + s
    s = s.rstrip("/") or "/"
    return s


def _build_system_prompt(current_path: Optional[str]) -> str:
    lines = [
        "你是 Foxel 的 AI 助手。",
        "你可以通过工具对文件/目录进行查询、读写、移动、复制、删除，以及运行处理器（processor）。",
        "",
        "可用工具：",
        "- time：获取服务器当前时间（精确到秒，英文星期），支持 year/month/day/hour/minute/second 偏移。",
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
        "1) 读操作（vfs_list_dir/vfs_stat/vfs_read_text/vfs_search）可直接调用工具。",
        "2) 写/改/删操作（vfs_write_text/vfs_mkdir/vfs_delete/vfs_move/vfs_copy/vfs_rename/processors_run）默认需要用户确认；只有在开启自动执行时才应直接执行。",
        "3) 用户未给出明确路径时先追问；若提供了“当前文件管理目录”，可以基于它把相对描述补全为绝对路径（以 / 开头）。",
        "4) 修改文件内容：先读取（vfs_read_text）→给出改动点→确认后再写入（vfs_write_text）。",
        "5) processors_run 返回任务 id 后，说明任务已提交，可在任务队列查看进度。",
        "6) 回答保持简洁中文。",
    ]
    if current_path:
        lines.append("")
        lines.append(f"当前文件管理目录：{current_path}")
    return "\n".join(lines)


def _ensure_tool_call_ids(message: Dict[str, Any]) -> Dict[str, Any]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return message

    changed = False
    for idx, call in enumerate(tool_calls):
        if not isinstance(call, dict):
            continue
        call_id = call.get("id")
        if isinstance(call_id, str) and call_id.strip():
            continue
        call["id"] = f"call_{idx}"
        changed = True

    if changed:
        message["tool_calls"] = tool_calls
    return message


def _extract_pending(tool_call: Dict[str, Any], requires_confirmation: bool) -> PendingToolCall:
    call_id = str(tool_call.get("id") or "")
    fn = tool_call.get("function") or {}
    name = str((fn.get("name") if isinstance(fn, dict) else None) or "")
    raw_args = fn.get("arguments") if isinstance(fn, dict) else None
    arguments: Dict[str, Any] = {}
    if isinstance(raw_args, str) and raw_args.strip():
        try:
            parsed = json.loads(raw_args)
            if isinstance(parsed, dict):
                arguments = parsed
        except json.JSONDecodeError:
            arguments = {}
    return PendingToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        requires_confirmation=requires_confirmation,
    )


def _find_last_assistant_tool_calls(messages: List[Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            return idx, msg
    raise HTTPException(status_code=400, detail="没有可确认的待执行操作")


def _existing_tool_result_ids(messages: List[Dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        tool_call_id = msg.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id.strip():
            ids.add(tool_call_id)
    return ids


async def _choose_chat_ability() -> str:
    tools_model = await AIProviderService.get_default_model("tools")
    return "tools" if tools_model else "chat"


def _sse(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _format_exc(exc: BaseException) -> str:
    text = str(exc)
    return text if text else exc.__class__.__name__


class AgentService:
    @classmethod
    async def chat(cls, req: AgentChatRequest, user: Optional[User]) -> Dict[str, Any]:
        history: List[Dict[str, Any]] = list(req.messages or [])
        current_path = _normalize_path(req.context.current_path if req.context else None)

        system_prompt = _build_system_prompt(current_path)
        internal_messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}] + history

        new_messages: List[Dict[str, Any]] = []
        pending: List[PendingToolCall] = []

        approved_ids = {i for i in (req.approved_tool_call_ids or []) if isinstance(i, str) and i.strip()}
        rejected_ids = {i for i in (req.rejected_tool_call_ids or []) if isinstance(i, str) and i.strip()}

        if approved_ids or rejected_ids:
            _, last_call_msg = _find_last_assistant_tool_calls(internal_messages)
            last_call_msg = _ensure_tool_call_ids(last_call_msg)
            tool_calls = last_call_msg.get("tool_calls") or []
            call_map: Dict[str, Dict[str, Any]] = {
                str(c.get("id")): c
                for c in tool_calls
                if isinstance(c, dict) and isinstance(c.get("id"), str)
            }

            existing_ids = _existing_tool_result_ids(internal_messages)
            for call_id in approved_ids | rejected_ids:
                if call_id in existing_ids:
                    continue
                tool_call = call_map.get(call_id)
                if not tool_call:
                    continue
                fn = tool_call.get("function") or {}
                name = fn.get("name") if isinstance(fn, dict) else None
                args_raw = fn.get("arguments") if isinstance(fn, dict) else None
                args: Dict[str, Any] = {}
                if isinstance(args_raw, str) and args_raw.strip():
                    try:
                        parsed = json.loads(args_raw)
                        if isinstance(parsed, dict):
                            args = parsed
                    except json.JSONDecodeError:
                        args = {}

                spec = get_tool(str(name or ""))
                if call_id in rejected_ids:
                    content = tool_result_to_content({"canceled": True, "reason": "user_rejected"})
                    tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                    internal_messages.append(tool_msg)
                    new_messages.append(tool_msg)
                    continue

                if not spec:
                    content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                    tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                    internal_messages.append(tool_msg)
                    new_messages.append(tool_msg)
                    continue

                try:
                    result = await spec.handler(args)
                    content = tool_result_to_content(result)
                except Exception as exc:  # noqa: BLE001
                    content = tool_result_to_content({"error": str(exc)})
                tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                internal_messages.append(tool_msg)
                new_messages.append(tool_msg)

        tools_schema = openai_tools()
        ability = await _choose_chat_ability()
        max_loops = 4

        for _ in range(max_loops):
            try:
                assistant = await chat_completion(
                    internal_messages,
                    ability=ability,
                    tools=tools_schema,
                    tool_choice="auto",
                    timeout=60.0,
                )
            except MissingModelError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except httpx.HTTPStatusError as exc:
                raise HTTPException(status_code=502, detail=f"对话请求失败: {exc}") from exc
            except httpx.RequestError as exc:
                raise HTTPException(status_code=502, detail=f"对话请求异常: {exc}") from exc

            assistant = _ensure_tool_call_ids(assistant)
            internal_messages.append(assistant)
            new_messages.append(assistant)

            tool_calls = assistant.get("tool_calls")
            if not isinstance(tool_calls, list) or not tool_calls:
                break

            pending = []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                call_id = str(call.get("id") or "")
                fn = call.get("function") or {}
                name = fn.get("name") if isinstance(fn, dict) else None
                args_raw = fn.get("arguments") if isinstance(fn, dict) else None
                args: Dict[str, Any] = {}
                if isinstance(args_raw, str) and args_raw.strip():
                    try:
                        parsed = json.loads(args_raw)
                        if isinstance(parsed, dict):
                            args = parsed
                    except json.JSONDecodeError:
                        args = {}

                spec = get_tool(str(name or ""))
                if not spec:
                    content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                    tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                    internal_messages.append(tool_msg)
                    new_messages.append(tool_msg)
                    continue

                if spec.requires_confirmation and not req.auto_execute:
                    pending.append(_extract_pending(call, True))
                    continue

                try:
                    result = await spec.handler(args)
                    content = tool_result_to_content(result)
                except Exception as exc:  # noqa: BLE001
                    content = tool_result_to_content({"error": str(exc)})
                tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                internal_messages.append(tool_msg)
                new_messages.append(tool_msg)

            if pending:
                break

        payload: Dict[str, Any] = {"messages": new_messages}
        if pending:
            payload["pending_tool_calls"] = [p.model_dump() for p in pending]
        return payload

    @classmethod
    async def chat_stream(cls, req: AgentChatRequest, user: Optional[User]):
        history: List[Dict[str, Any]] = list(req.messages or [])
        current_path = _normalize_path(req.context.current_path if req.context else None)

        system_prompt = _build_system_prompt(current_path)
        internal_messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}] + history

        new_messages: List[Dict[str, Any]] = []
        pending: List[PendingToolCall] = []

        approved_ids = {i for i in (req.approved_tool_call_ids or []) if isinstance(i, str) and i.strip()}
        rejected_ids = {i for i in (req.rejected_tool_call_ids or []) if isinstance(i, str) and i.strip()}

        try:
            if approved_ids or rejected_ids:
                _, last_call_msg = _find_last_assistant_tool_calls(internal_messages)
                last_call_msg = _ensure_tool_call_ids(last_call_msg)
                tool_calls = last_call_msg.get("tool_calls") or []
                call_map: Dict[str, Dict[str, Any]] = {
                    str(c.get("id")): c
                    for c in tool_calls
                    if isinstance(c, dict) and isinstance(c.get("id"), str)
                }

                existing_ids = _existing_tool_result_ids(internal_messages)
                for call_id in approved_ids | rejected_ids:
                    if call_id in existing_ids:
                        continue
                    tool_call = call_map.get(call_id)
                    if not tool_call:
                        continue
                    fn = tool_call.get("function") or {}
                    name = fn.get("name") if isinstance(fn, dict) else None
                    args_raw = fn.get("arguments") if isinstance(fn, dict) else None
                    args: Dict[str, Any] = {}
                    if isinstance(args_raw, str) and args_raw.strip():
                        try:
                            parsed = json.loads(args_raw)
                            if isinstance(parsed, dict):
                                args = parsed
                        except json.JSONDecodeError:
                            args = {}

                    spec = get_tool(str(name or ""))
                    if call_id in rejected_ids:
                        content = tool_result_to_content({"canceled": True, "reason": "user_rejected"})
                        tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                        internal_messages.append(tool_msg)
                        new_messages.append(tool_msg)
                        yield _sse("tool_end", {"tool_call_id": call_id, "name": str(name or ""), "message": tool_msg})
                        continue

                    if not spec:
                        content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                        tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                        internal_messages.append(tool_msg)
                        new_messages.append(tool_msg)
                        yield _sse("tool_end", {"tool_call_id": call_id, "name": str(name or ""), "message": tool_msg})
                        continue

                    yield _sse("tool_start", {"tool_call_id": call_id, "name": spec.name})
                    try:
                        result = await spec.handler(args)
                        content = tool_result_to_content(result)
                    except Exception as exc:  # noqa: BLE001
                        content = tool_result_to_content({"error": str(exc)})
                    tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                    internal_messages.append(tool_msg)
                    new_messages.append(tool_msg)
                    yield _sse("tool_end", {"tool_call_id": call_id, "name": spec.name, "message": tool_msg})

            tools_schema = openai_tools()
            ability = await _choose_chat_ability()
            max_loops = 4

            for _ in range(max_loops):
                assistant_event_id = uuid.uuid4().hex
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
                        if event.get("type") == "delta":
                            delta = event.get("delta")
                            if isinstance(delta, str) and delta:
                                yield _sse("assistant_delta", {"id": assistant_event_id, "delta": delta})
                        elif event.get("type") == "message":
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

                assistant_message = _ensure_tool_call_ids(assistant_message)
                internal_messages.append(assistant_message)
                new_messages.append(assistant_message)
                yield _sse("assistant_end", {"id": assistant_event_id, "message": assistant_message})

                tool_calls = assistant_message.get("tool_calls")
                if not isinstance(tool_calls, list) or not tool_calls:
                    break

                pending = []
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    call_id = str(call.get("id") or "")
                    fn = call.get("function") or {}
                    name = fn.get("name") if isinstance(fn, dict) else None
                    args_raw = fn.get("arguments") if isinstance(fn, dict) else None
                    args: Dict[str, Any] = {}
                    if isinstance(args_raw, str) and args_raw.strip():
                        try:
                            parsed = json.loads(args_raw)
                            if isinstance(parsed, dict):
                                args = parsed
                        except json.JSONDecodeError:
                            args = {}

                    spec = get_tool(str(name or ""))
                    if not spec:
                        content = tool_result_to_content({"error": f"unknown_tool: {name}"})
                        tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                        internal_messages.append(tool_msg)
                        new_messages.append(tool_msg)
                        yield _sse("tool_end", {"tool_call_id": call_id, "name": str(name or ""), "message": tool_msg})
                        continue

                    if spec.requires_confirmation and not req.auto_execute:
                        pending.append(_extract_pending(call, True))
                        continue

                    yield _sse("tool_start", {"tool_call_id": call_id, "name": spec.name})
                    try:
                        result = await spec.handler(args)
                        content = tool_result_to_content(result)
                    except Exception as exc:  # noqa: BLE001
                        content = tool_result_to_content({"error": str(exc)})
                    tool_msg = {"role": "tool", "tool_call_id": call_id, "content": content}
                    internal_messages.append(tool_msg)
                    new_messages.append(tool_msg)
                    yield _sse("tool_end", {"tool_call_id": call_id, "name": spec.name, "message": tool_msg})

                if pending:
                    yield _sse("pending", {"pending_tool_calls": [p.model_dump() for p in pending]})
                    break

            payload: Dict[str, Any] = {"messages": new_messages}
            if pending:
                payload["pending_tool_calls"] = [p.model_dump() for p in pending]
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
                payload["pending_tool_calls"] = [p.model_dump() for p in pending]
            yield _sse("done", payload)
            return
        except Exception as exc:  # noqa: BLE001
            new_messages.append({"role": "assistant", "content": f"服务端异常: {_format_exc(exc)}"})
            payload: Dict[str, Any] = {"messages": new_messages}
            if pending:
                payload["pending_tool_calls"] = [p.model_dump() for p in pending]
            yield _sse("done", payload)
            return
