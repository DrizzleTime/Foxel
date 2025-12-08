from fastapi import Request, status
from fastapi.responses import JSONResponse

async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal Server Error", "detail": str(exc)},
    )
