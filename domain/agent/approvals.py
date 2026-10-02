import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from models.database import AgentApprovalBatch, AgentApprovalCall
from .tools.base import tool_error, tool_result_to_content


def now():
    return datetime.now(timezone.utc)


def pending_call(call: AgentApprovalCall) -> dict[str, Any]:
    return {"id": call.call_id, "name": call.name, "arguments": call.arguments,
            "requires_confirmation": call.requires_confirmation, "status": call.status}


def result_message(call: AgentApprovalCall) -> dict[str, Any]:
    content = call.result or tool_result_to_content(tool_error("operation_in_progress"))
    return {"role": "tool", "mcp_call_id": call.call_id, "content": content}


async def create_batch(user_id: int, assistant: dict[str, Any], tool_index: dict[str, Any]) -> AgentApprovalBatch:
    async with in_transaction() as connection:
        batch = await AgentApprovalBatch.create(
            id=str(uuid.uuid4()), user_id=user_id, assistant_message=assistant,
            expires_at=now() + timedelta(hours=24), using_db=connection,
        )
        await AgentApprovalCall.bulk_create([
            AgentApprovalCall(batch_id=batch.id, call_id=call["id"], position=position,
                              name=call["name"], arguments=call.get("arguments", {}),
                              requires_confirmation=bool(tool_index.get(call["name"], {}).get("meta", {}).get("requires_confirmation", True)))
            for position, call in enumerate(assistant["mcp_calls"])
        ], using_db=connection)
    return batch


async def load_batch(batch_id: str, user_id: int, approved: set[str], rejected: set[str]):
    batch = await AgentApprovalBatch.get_or_none(id=batch_id, user_id=user_id)
    if batch is None:
        raise HTTPException(400, detail="invalid_approval_batch")
    calls = await AgentApprovalCall.filter(batch_id=batch.id).order_by("position")
    if approved & rejected or (approved | rejected) - {call.call_id for call in calls}:
        raise HTTPException(400, detail="invalid_approval_ids")
    if batch.expires_at <= now():
        await AgentApprovalCall.filter(batch_id=batch.id, status="pending").update(
            status="expired", result=tool_result_to_content(tool_error("approval_expired")), updated_at=now(),
        )
        raise HTTPException(400, detail="approval_expired")
    cutoff = now() - timedelta(days=7)
    expired_ids = await AgentApprovalBatch.filter(expires_at__lt=now()).values_list("id", flat=True)
    if expired_ids:
        await AgentApprovalCall.filter(batch_id__in=expired_ids, status="pending").update(
            status="expired", result=tool_result_to_content(tool_error("approval_expired")), updated_at=now(),
        )
    stale = await AgentApprovalBatch.filter(expires_at__lt=cutoff, executing=False).exclude(
        continuation_status="running"
    ).values_list("id", flat=True)
    for stale_id in stale:
        if not await AgentApprovalCall.filter(batch_id=stale_id, status__in=["pending", "running"]).exists() and not await AgentApprovalCall.filter(batch_id=stale_id, updated_at__gte=cutoff).exists():
            await AgentApprovalBatch.filter(id=stale_id).delete()
    return batch, calls


async def execute_call(call: AgentApprovalCall, execute, *, rejected: bool = False) -> AgentApprovalCall:
    claimed = await AgentApprovalCall.filter(id=call.id, status="pending").update(status="running", updated_at=now())
    if not claimed:
        return await AgentApprovalCall.get(id=call.id)
    if rejected:
        content = tool_result_to_content({"canceled": True, "reason": "user_rejected"})
        status = "rejected"
    else:
        # Cancellation intentionally leaves running: retrying an uncertain write is unsafe.
        try:
            content = await execute(call.name, call.arguments)
        except Exception:
            content = tool_result_to_content(tool_error("execution_failed"))
        try:
            status = "failed" if json.loads(content).get("ok") is False else "succeeded"
        except (ValueError, AttributeError):
            status = "succeeded"
    await AgentApprovalCall.filter(id=call.id, status="running").update(status=status, result=content, updated_at=now())
    return await AgentApprovalCall.get(id=call.id)
