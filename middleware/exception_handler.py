import logging
from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import httpx

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if exc.detail is not None else str(exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTPException", "detail": detail},
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation Error", "detail": exc.errors()},
    )


async def httpx_exception_handler(request: Request, exc: httpx.HTTPStatusError):
    resp = exc.response
    status_code = resp.status_code if resp is not None else status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = None
    if resp is not None:
        detail = resp.text or resp.reason_phrase
    if not detail:
        detail = str(exc)
    return JSONResponse(
        status_code=status_code,
        content={"error": "Upstream HTTP error", "detail": detail},
    )


async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal Server Error", "detail": str(exc)},
    )
