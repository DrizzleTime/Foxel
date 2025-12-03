from dataclasses import asdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from api.response import page, success
from application.logging.dependencies import logging_service

router = APIRouter(prefix="/api/logs", tags=["Logs"])

@router.get("")
async def get_logs(
    page_num: int = Query(1, alias="page"),
    page_size: int = Query(20, alias="page_size"),
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
):
    """获取日志列表，支持分页和筛选"""
    logs, total = await logging_service.list_logs(
        page=page_num,
        page_size=page_size,
        level=level,
        source=source,
        start_time=start_time,
        end_time=end_time,
    )
    items = [asdict(log) for log in logs]
    return success(page(items, total, page_num, page_size))

@router.delete("")
async def clear_logs(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
):
    """清理指定时间范围内的日志"""
    deleted_count = await logging_service.clear_logs(
        start_time=start_time, end_time=end_time
    )
    return success({"deleted_count": deleted_count})
