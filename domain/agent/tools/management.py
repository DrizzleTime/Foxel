"""Storage and automation management using the same services and access as the API."""

import re
from datetime import datetime
from typing import Any

from domain.adapters.service import AdapterService
from domain.adapters.types import AdapterCreate
from domain.auth import User
from domain.permission.execution import ExecutionError, current_user_id, normalize_path
from domain.permission.service import PermissionService
from domain.permission.types import AdapterPermission
from domain.processors import ProcessorService
from domain.tasks.scheduler import task_scheduler
from domain.tasks.service import TaskService
from domain.tasks.types import AutomationTaskCreate, AutomationTaskRead
from models.database import UserAccount

from .base import ToolSpec


async def _user(permission: str | None = None) -> User:
    account = await UserAccount.get_or_none(id=current_user_id(), disabled=False)
    if account is None:
        raise ExecutionError("permission_denied")
    if permission and not await PermissionService.check_system_permission(account.id, permission):
        raise ExecutionError("permission_denied")
    return User.model_validate(account, from_attributes=True)


async def _adapters_available(_: dict[str, Any]) -> dict[str, Any]:
    await _user(AdapterPermission.LIST)
    return {"adapters": await AdapterService.available_adapter_types()}


async def _adapters_list(_: dict[str, Any]) -> dict[str, Any]:
    await _user(AdapterPermission.LIST)
    # Existing credentials must not be copied into the model conversation.
    return {"adapters": [
        item.model_dump(exclude={"config"}) for item in await AdapterService.list_adapters()
    ]}


async def _adapters_create(args: dict[str, Any]) -> dict[str, Any]:
    user = await _user(AdapterPermission.CREATE)
    payload = AdapterCreate.model_validate(args)
    payload.name = payload.name.strip()
    if not payload.name:
        raise ExecutionError("invalid_arguments")
    adapter = await AdapterService.create_adapter(payload, user)
    return adapter.model_dump(exclude={"config"})


def _processor_config(processor: Any, config: dict[str, Any]) -> dict[str, Any]:
    config = dict(config)
    for field in getattr(processor, "config_schema", []):
        key = field["key"]
        if key not in config and "default" in field:
            config[key] = field["default"]
        value = config.get(key)
        if value is None or value == "":
            if field.get("required"):
                raise ExecutionError("invalid_arguments")
            continue
        kind = field.get("type")
        if kind in {"string", "password"} and not isinstance(value, str):
            raise ExecutionError("invalid_arguments")
        if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ExecutionError("invalid_arguments")
        if kind == "boolean" and not isinstance(value, bool):
            raise ExecutionError("invalid_arguments")
        if kind == "select":
            options = [item.get("value") if isinstance(item, dict) else item for item in field.get("options", [])]
            if value not in options:
                raise ExecutionError("invalid_arguments")
    return config


async def _tasks_list(_: dict[str, Any]) -> dict[str, Any]:
    await _user()
    return {"tasks": [
        AutomationTaskRead.model_validate(item).model_dump() for item in await TaskService.list_tasks()
    ]}


async def _tasks_create(args: dict[str, Any]) -> dict[str, Any]:
    user = await _user()
    payload = AutomationTaskCreate.model_validate(args)
    payload.name = payload.name.strip()
    if not payload.name or payload.event not in {"file_written", "file_deleted", "cron"}:
        raise ExecutionError("invalid_arguments")
    processor = ProcessorService.get_processor(payload.processor_type)
    if processor is None:
        raise ExecutionError("unsupported_capability")
    payload.processor_config = _processor_config(processor, payload.processor_config)
    trigger = payload.trigger_config
    if payload.event == "cron":
        if set(trigger) - {"cron_expr", "path"}:
            raise ExecutionError("invalid_arguments")
        expression = trigger.get("cron_expr")
        path = trigger.get("path")
        if not isinstance(expression, str) or task_scheduler._build_cron(expression, datetime.now()) is None:
            raise ExecutionError("invalid_arguments")
        if not isinstance(path, str) or not path.strip().startswith("/"):
            raise ExecutionError("invalid_arguments")
        payload.trigger_config = {"cron_expr": expression.strip(), "path": normalize_path(path)}
    else:
        if set(trigger) - {"path_prefix", "filename_regex"}:
            raise ExecutionError("invalid_arguments")
        path = trigger.get("path_prefix")
        if path is not None:
            if not isinstance(path, str) or (path and not path.strip().startswith("/")):
                raise ExecutionError("invalid_arguments")
            if path:
                trigger["path_prefix"] = normalize_path(path)
        pattern = trigger.get("filename_regex")
        if pattern is not None:
            if not isinstance(pattern, str):
                raise ExecutionError("invalid_arguments")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ExecutionError("invalid_arguments") from exc
        payload.trigger_config = trigger
    task = await TaskService.create_task(payload, user)
    return AutomationTaskRead.model_validate(task).model_dump()


EMPTY_PARAMETERS = {"type": "object", "properties": {}, "additionalProperties": False}

TOOLS = {
    "adapters_available": ToolSpec(
        name="adapters_available",
        description="Discover supported storage adapter types and their config_schema before creating an adapter. Requires adapter.list permission. Ask the user for required fields; never invent credentials.",
        parameters=EMPTY_PARAMETERS,
        requires_confirmation=False,
        handler=_adapters_available,
    ),
    "adapters_list": ToolSpec(
        name="adapters_list",
        description="List existing storage adapters, including id, name, type, mount path, sub_path and enabled status, without credentials. Use to check mount path conflicts before creation. Requires adapter.list permission.",
        parameters=EMPTY_PARAMETERS,
        requires_confirmation=False,
        handler=_adapters_list,
    ),
    "adapters_create": ToolSpec(
        name="adapters_create",
        description="Create and mount a storage adapter. Discover types and required config with adapters_available first. Confirm the name, mount path, storage credentials and enabled state with the user. Requires adapter.create permission and execution confirmation. Returns the created adapter without credentials.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "User-facing adapter name."},
                "type": {"type": "string", "description": "Storage type returned by adapters_available."},
                "path": {"type": "string", "description": "Absolute Foxel mount path, e.g. /backup. This is not the storage provider's root path."},
                "config": {"type": "object", "description": "Storage settings following the discovered config_schema. Use only credentials supplied by the user."},
                "sub_path": {"type": "string", "description": "Optional subdirectory within the storage provider."},
                "enabled": {"type": "boolean", "description": "Whether the adapter is enabled. Defaults to true."},
            },
            "required": ["name", "type", "path", "config"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_adapters_create,
    ),
    "tasks_list": ToolSpec(
        name="tasks_list",
        description="List configured automation tasks and their trigger and processor settings. These are persistent automation rules, not task queue executions. Requires an active account, matching the automation API.",
        parameters=EMPTY_PARAMETERS,
        requires_confirmation=False,
        handler=_tasks_list,
    ),
    "tasks_create": ToolSpec(
        name="tasks_create",
        description="Create a persistent automation task for file_written, file_deleted or cron. Use processors_list first to discover processor_type and processor_config. Ask for missing trigger/action details and explain the schedule, target paths and action before confirmation. Requires an active account and execution confirmation. This creates a rule; it does not run a one-off processor job.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "User-facing automation task name."},
                "event": {"type": "string", "enum": ["file_written", "file_deleted", "cron"]},
                "processor_type": {"type": "string", "description": "A type returned by processors_list."},
                "trigger_config": {"type": "object", "description": "For cron: cron_expr and absolute Foxel path are required. Cron accepts five fields (minute hour day month weekday) or six fields with seconds FIRST, in server local time. For file events: optional absolute path_prefix and filename_regex; omitting filters applies to all paths."},
                "processor_config": {"type": "object", "description": "Configuration following the processor's config_schema."},
                "enabled": {"type": "boolean", "description": "Whether the rule is enabled. Defaults to true."},
            },
            "required": ["name", "event", "processor_type", "trigger_config"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
        handler=_tasks_create,
    ),
}
