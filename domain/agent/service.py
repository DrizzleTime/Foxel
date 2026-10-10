import asyncio
import json
import logging
import uuid
from contextlib import aclosing
from typing import Any

import httpx
from fastapi import HTTPException

from domain.ai import AIProviderService, MissingModelError, chat_completion, chat_completion_stream
from domain.auth import User
from domain.permission.execution import ExecutionError, normalize_path
from models.database import AgentApprovalBatch, AgentApprovalCall

from .approvals import create_batch, execute_call, load_batch, pending_call, result_message
from .mcp import mcp_client_session, mcp_content_to_text
from .execution import execute_tool
from .tools import AGENT_ONLY_TOOL_NAMES, mcp_tool_descriptors
from .tools.base import tool_error, tool_result_to_content
from .types import AgentChatRequest

logger = logging.getLogger(__name__)


def _build_system_prompt(current_path: str | None) -> str:
    text = (
        "你是 Foxel 的 AI 助手。使用提供的 MCP 工具查询、读取、写入、移动、复制、删除文件，"
        "抓取网页、获取时间或提交处理器任务。回答语言跟随用户，尽量简洁。\n"
        "查询工具可直接执行。web_fetch 的所有 HTTP 方法均免审批，但可能修改外部系统。\n"
        "文件写入、创建、删除、移动、复制、重命名和 processors_run 默认需要用户确认；"
        "开启自动执行时可直接执行。审批不授予路径权限。\n"
        "路径必须是以 / 开头的绝对路径；未提供明确路径时追问，或基于当前文件管理目录补全。\n"
        "修改文本前先读取并说明改动，再申请写入。processors_run 返回 task_id 只代表已提交，"
        "请用户到任务队列查看进度。当前不提供任务查询、外部 MCP、后台持续 Agent 或长期记忆。"
    )
    return text + (f"\n当前文件管理目录：{current_path}" if current_path else "")


def _ensure_mcp_call_ids(message: dict[str, Any]) -> dict[str, Any]:
    calls = message.get("mcp_calls")
    if not isinstance(calls, list):
        return message
    seen, valid = set(), []
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get("name"), str):
            continue
        call = dict(call)
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id.strip() or call_id in seen or len(call_id) > 255:
            call_id = "call_" + uuid.uuid4().hex
        seen.add(call_id)
        call["id"] = call_id
        if not isinstance(call.get("arguments"), dict):
            call["arguments"] = {}
        valid.append(call)
    return {**message, "mcp_calls": valid}


def _tool_requires_confirmation(descriptor: dict[str, Any]) -> bool:
    meta = descriptor.get("meta") or {}
    return bool(meta.get("requires_confirmation", not (descriptor.get("annotations") or {}).get("readOnlyHint")))


async def _choose_chat_ability() -> str:
    ability = "tools" if await AIProviderService.get_default_model("tools") else "chat"
    model = await AIProviderService.get_default_model(ability)
    if model is None:
        raise MissingModelError(f"未配置默认 {ability} 模型，请前往系统设置完成配置。")
    if getattr(model, "provider", None) is None:
        await model.fetch_related("provider")
    if str(model.provider.api_format).lower() not in {"openai", "anthropic", "ollama"}:
        raise MissingModelError("Agent 当前支持 OpenAI、Anthropic 和 Ollama 对话接口。")
    return ability


def _sse(event: str, data: Any) -> bytes:
    return ("event: " + event + "\ndata: " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode()


async def _list_mcp_tools(session) -> list[dict[str, Any]]:
    result = await session.list_tools()
    tools = [{"name": item.name, "description": item.description or "", "input_schema": item.input_schema or {},
              "annotations": item.annotations.model_dump(exclude_none=True) if item.annotations else {},
              "meta": item.meta or {}} for item in result.tools]
    tools.extend(
        {"name": item.name, "description": item.description, "input_schema": item.input_schema,
         "annotations": item.annotations, "meta": item.meta}
        for item in mcp_tool_descriptors(include_agent_only=True) if item.name in AGENT_ONLY_TOOL_NAMES
    )
    return tools


async def _execute_mcp_call(session, name: str, arguments: dict[str, Any]) -> str:
    try:
        result = await session.call_tool(name, arguments)
        if getattr(result, "is_error", False):
            return tool_result_to_content(tool_error("invalid_arguments"))
        return mcp_content_to_text(result.content, result.structured_content)
    except Exception:
        # Without the tool name an adapter-level failure is indistinguishable
        # from a bad-arguments failure, because both return execution_failed.
        logger.exception("MCP tool call failed (tool=%s)", name)
        return tool_result_to_content(tool_error("execution_failed"))


async def validate_request(req: AgentChatRequest, user: User):
    approved, rejected = set(req.approved_mcp_call_ids), set(req.rejected_mcp_call_ids)
    if approved & rejected:
        raise HTTPException(400, detail="invalid_approval_ids")
    if (approved or rejected) and not req.approval_batch_id:
        raise HTTPException(400, detail="approval_batch_required: 请重新生成待审批操作。")
    if req.context and req.context.current_path:
        try:
            normalize_path(req.context.current_path)
        except ExecutionError:
            raise HTTPException(400, detail="invalid_arguments") from None
    if req.approval_batch_id:
        return await load_batch(req.approval_batch_id, user.id, approved, rejected)
    answered = {m.get("mcp_call_id") for m in req.messages if m.get("role") == "tool"}
    if any(c.get("id") not in answered for m in req.messages if m.get("role") == "assistant"
           for c in (m.get("mcp_calls") or []) if isinstance(c, dict)):
        raise HTTPException(400, detail="approval_batch_required: 请重新生成待审批操作。")
    return None


class AgentService:
    @classmethod
    async def _run(cls, req: AgentChatRequest, user: User, streaming: bool):
        validated = await validate_request(req, user)
        path = normalize_path(req.context.current_path) if req.context and req.context.current_path else None
        history = [dict(m) for m in req.messages if m.get("role") in {"user", "assistant", "tool"}]
        messages: list[dict[str, Any]] = []
        batch_id, pending = req.approval_batch_id, []
        replace = bool(validated)
        continuation_owned = False
        execution_owned = False

        def payload(reason: str):
            return {"messages": history + messages if replace else messages,
                    "replace_messages": replace, "pending_mcp_calls": pending,
                    "approval_batch_id": batch_id if pending else None, "finish_reason": reason}

        async def finish(reason: str):
            data = payload(reason)
            if continuation_owned:
                await AgentApprovalBatch.filter(id=req.approval_batch_id, continuation_status="running").update(
                    continuation_status="completed", continuation_result=data,
                )
            return data

        try:
            async with mcp_client_session(user, path) as session:
                tools = await _list_mcp_tools(session)
                index = {tool["name"]: tool for tool in tools}

                async def execute(name, arguments):
                    if name in AGENT_ONLY_TOOL_NAMES:
                        return tool_result_to_content(await execute_tool(name, arguments, user, path))
                    return await _execute_mcp_call(session, name, arguments)

                if validated:
                    batch, calls = validated
                    if batch.continuation_result is not None:
                        yield "done", batch.continuation_result
                        return
                    approved, rejected = set(req.approved_mcp_call_ids), set(req.rejected_mcp_call_ids)
                    # Replace the last tool-call turn with its authoritative batch.
                    last = next((i for i in range(len(history) - 1, -1, -1)
                                 if history[i].get("role") == "assistant" and history[i].get("mcp_calls")), None)
                    history = history + [batch.assistant_message] if last is None else history[:last] + [batch.assistant_message]
                    execution_owned = bool(await AgentApprovalBatch.filter(id=batch.id, executing=False).update(executing=True))
                    calls = await AgentApprovalCall.filter(batch_id=batch.id).order_by("position")
                    if not execution_owned or any(call.status == "running" for call in calls):
                        messages.extend(result_message(call) for call in calls if call.result is not None)
                        pending = [pending_call(call) for call in calls if call.status in {"pending", "running"}]
                        yield "pending", {"pending_mcp_calls": pending, "approval_batch_id": batch.id}
                        yield "done", {**payload("operation_in_progress"), "approval_batch_id": batch.id}
                        return
                    for call in calls:
                        if call.call_id in approved | rejected:
                            if call.status == "pending" and call.call_id in approved:
                                yield "mcp_call_start", {"mcp_call_id": call.call_id, "name": call.name}
                            call = await execute_call(call, execute, rejected=call.call_id in rejected)
                            yield "mcp_call_end", {"mcp_call_id": call.call_id, "name": call.name, "message": result_message(call)}
                            if call.status == "running":
                                break
                    calls = await AgentApprovalCall.filter(batch_id=batch.id).order_by("position")
                    messages.extend(result_message(call) for call in calls if call.result is not None)
                    pending = [pending_call(call) for call in calls if call.status in {"pending", "running"}]
                    if pending:
                        yield "pending", {"pending_mcp_calls": pending, "approval_batch_id": batch_id}
                        yield "done", await finish("operation_in_progress" if any(c["status"] == "running" for c in pending) else "pending_approval")
                        return
                    continuation_owned = bool(await AgentApprovalBatch.filter(id=batch.id, continuation_status="pending").update(continuation_status="running"))
                    if not continuation_owned:
                        batch = await AgentApprovalBatch.get(id=batch.id)
                        data = batch.continuation_result or {**payload("operation_in_progress"), "approval_batch_id": batch.id}
                        yield "done", data
                        return

                ability = await _choose_chat_ability()
                internal = [{"role": "system", "content": _build_system_prompt(path)}] + history + messages
                for _ in range(8):
                    event_id = str(uuid.uuid4())
                    yield "assistant_start", {"id": event_id}
                    assistant = None
                    if streaming:
                        async for event in chat_completion_stream(internal, ability=ability, tools=tools, tool_choice="auto", timeout=60.0):
                            if event.get("type") == "delta" and event.get("delta"):
                                yield "assistant_delta", {"id": event_id, "delta": event["delta"]}
                            elif event.get("type") == "message":
                                assistant = event.get("message")
                    else:
                        assistant = await chat_completion(internal, ability=ability, tools=tools, tool_choice="auto", timeout=60.0)
                    assistant = _ensure_mcp_call_ids(assistant or {"role": "assistant", "content": ""})
                    internal.append(assistant)
                    messages.append(assistant)
                    yield "assistant_end", {"id": event_id, "message": assistant}
                    calls = assistant.get("mcp_calls") or []
                    if not calls:
                        yield "done", await finish("completed")
                        return
                    needs_approval = not req.auto_execute and any(
                        _tool_requires_confirmation(index.get(call["name"], {})) for call in calls
                    )
                    batch = await create_batch(user.id, assistant, index) if needs_approval else None
                    records = await AgentApprovalCall.filter(batch_id=batch.id).order_by("position") if batch else []
                    for position, call in enumerate(calls):
                        if needs_approval and _tool_requires_confirmation(index.get(call["name"], {})):
                            continue
                        yield "mcp_call_start", {"mcp_call_id": call["id"], "name": call["name"]}
                        if batch:
                            record = await execute_call(records[position], execute)
                            message = result_message(record)
                        else:
                            message = {"role": "tool", "mcp_call_id": call["id"], "content": await execute(call["name"], call["arguments"])}
                        messages.append(message)
                        internal.append(message)
                        yield "mcp_call_end", {"mcp_call_id": call["id"], "name": call["name"], "message": message}
                    if batch:
                        batch_id = batch.id
                        records = await AgentApprovalCall.filter(batch_id=batch.id).order_by("position")
                        pending = [pending_call(call) for call in records if call.status in {"pending", "running"}]
                        yield "pending", {"pending_mcp_calls": pending, "approval_batch_id": batch_id}
                        yield "done", await finish("pending_approval")
                        return
                messages.append({"role": "assistant", "content": "已达到本次 8 轮调用上限，已执行结果保留。请继续对话。"})
                yield "done", await finish("iteration_limit")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # The user only ever sees a generic message below, so the
            # traceback has to reach the server log to stay diagnosable.
            logger.exception(
                "Agent chat failed (user=%s, error=%s)", user.username, type(exc).__name__
            )
            if isinstance(exc, MissingModelError):
                content, reason = str(exc), "model_unavailable"
            elif isinstance(exc, httpx.TimeoutException):
                content, reason = "模型请求超时。", "request_timeout"
            else:
                content, reason = "请求执行失败，请稍后重试。", "execution_failed"
            messages.append({"role": "assistant", "content": content})
            yield "done", await finish(reason)
        finally:
            if execution_owned:
                await AgentApprovalBatch.filter(id=req.approval_batch_id).update(executing=False)

    @classmethod
    async def chat(cls, req: AgentChatRequest, user: User) -> dict[str, Any]:
        async with aclosing(cls._run(req, user, streaming=False)) as events:
            async for event, data in events:
                if event == "done":
                    return data
        return {"messages": []}

    @classmethod
    async def chat_stream(cls, req: AgentChatRequest, user: User):
        try:
            async with aclosing(cls._run(req, user, streaming=True)) as events:
                async for event, data in events:
                    yield _sse(event, data)
        except asyncio.CancelledError:
            return
