import traceback

from fastapi import Request, status
from fastapi.responses import JSONResponse

from application.logging.dependencies import logging_service


async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理
    """
    error_details = {
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "exception": str(exc),
        "traceback": traceback.format_exc(),
    }
    await logging_service.error(
        source="global_exception_handler",
        message=f"Unhandled exception: {exc}",
        details=error_details
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal Server Error", "detail": str(exc)},
    )
