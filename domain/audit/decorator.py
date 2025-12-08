import inspect
import time
from functools import wraps
from typing import Any, Dict, Mapping, Optional

import jwt
from fastapi import Request
from jwt.exceptions import InvalidTokenError

from domain.audit.service import AuditService
from domain.audit.types import AuditAction
from domain.auth.service import ALGORITHM
from domain.config.service import ConfigService
from models.database import UserAccount


def _extract_request(bound_args: Mapping[str, Any]) -> Request | None:
    for value in bound_args.values():
        if isinstance(value, Request):
            return value
    return None


async def _resolve_user(request: Request | None, user_obj: Any | None) -> tuple[Optional[int], Optional[str]]:
    user_id: int | None = None
    username: str | None = None

    if request:
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = jwt.decode(token, await ConfigService.get_secret_key("SECRET_KEY"), algorithms=[ALGORITHM])
                username = payload.get("sub") or payload.get("username")
                if username:
                    user = await UserAccount.get_or_none(username=username)
                    user_id = user.id if user else None
            except (InvalidTokenError, Exception):
                pass

    if user_id is None and username is None and user_obj is not None:
        user_id = getattr(user_obj, "id", None) or getattr(user_obj, "user_id", None)
        username = getattr(user_obj, "username", None) or getattr(user_obj, "name", None)
        if isinstance(user_obj, dict):
            user_id = user_obj.get("id", user_obj.get("user_id", user_id))
            username = user_obj.get("username", user_obj.get("name", username))

    return user_id, username


def _extract_body_fields(bound_args: Mapping[str, Any], body_fields: list[str] | None, redact_fields: list[str] | None):
    if not body_fields:
        return None
    body: Dict[str, Any] = {}
    redacts = set(redact_fields or [])
    for value in bound_args.values():
        data: Optional[Dict[str, Any]] = None
        if hasattr(value, "model_dump"):
            try:
                data = value.model_dump()
            except Exception:
                data = None
        elif hasattr(value, "dict"):
            try:
                data = value.dict()
            except Exception:
                data = None
        elif isinstance(value, dict):
            data = value
        elif hasattr(value, "__dict__"):
            data = dict(value.__dict__)
        if not isinstance(data, dict):
            continue
        for field in body_fields:
            if field in data and field not in body:
                body[field] = data[field]
    if not body:
        return None
    for field in redacts:
        if field in body:
            body[field] = "<redacted>"
    return body


def _build_request_params(request: Request | None) -> Dict[str, Any] | None:
    if not request:
        return None
    params: Dict[str, Any] = {}
    query = dict(request.query_params)
    if query:
        params["query"] = query
    path_params = dict(request.path_params or {})
    if path_params:
        params["path"] = path_params
    return params or None


def _status_code_from_response(response: Any) -> int:
    if hasattr(response, "status_code"):
        try:
            return int(getattr(response, "status_code"))
        except Exception:
            pass
    return 200


def audit(
    *,
    action: AuditAction,
    description: str | None = None,
    body_fields: list[str] | None = None,
    redact_fields: list[str] | None = None,
    user_kw: str = "current_user",
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            bound = inspect.signature(func).bind_partial(*args, **kwargs)
            bound.apply_defaults()
            request = _extract_request(bound.arguments)
            start = time.perf_counter()
            user_info = bound.arguments.get(user_kw)
            user_id, username = await _resolve_user(request, user_info)
            request_params = _build_request_params(request)
            request_body = _extract_body_fields(bound.arguments, body_fields, redact_fields)

            try:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                status_code = _status_code_from_response(result)
                success = True
                error = None
            except Exception as exc:  # noqa: BLE001
                status_code = getattr(exc, "status_code", 500)
                success = False
                error = str(exc)
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                try:
                    await AuditService.log(
                        action=action,
                        description=description,
                        user_id=user_id,
                        username=username,
                        client_ip=request.client.host if request and request.client else None,
                        method=request.method if request else "",
                        path=request.url.path if request else func.__name__,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        success=success,
                        request_params=request_params,
                        request_body=request_body,
                        error=error,
                    )
                except Exception:
                    pass
                raise

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            try:
                await AuditService.log(
                    action=action,
                    description=description,
                    user_id=user_id,
                    username=username,
                    client_ip=request.client.host if request and request.client else None,
                    method=request.method if request else "",
                    path=request.url.path if request else func.__name__,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    success=success,
                    request_params=request_params,
                    request_body=request_body,
                    error=error,
                )
            except Exception:
                pass
            return result

        return wrapper

    return decorator
