import calendar
from datetime import datetime, timedelta
from typing import Any, Dict

from .base import ToolSpec


def _parse_offset(args: Dict[str, Any], key: str) -> int:
    value = args.get(key)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _add_months(dt: datetime, months: int) -> datetime:
    if months == 0:
        return dt
    total = dt.year * 12 + (dt.month - 1) + months
    year = total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


async def _time(args: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now()
    year_offset = _parse_offset(args, "year")
    month_offset = _parse_offset(args, "month")
    day_offset = _parse_offset(args, "day")
    hour_offset = _parse_offset(args, "hour")
    minute_offset = _parse_offset(args, "minute")
    second_offset = _parse_offset(args, "second")

    dt = _add_months(now, year_offset * 12 + month_offset)
    dt = dt + timedelta(days=day_offset, hours=hour_offset, minutes=minute_offset, seconds=second_offset)

    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    weekday = weekday_names[dt.weekday()]
    dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "ok": True,
        "summary": f"{dt_str} · {weekday}",
        "data": {
            "datetime": dt_str,
            "weekday": weekday,
            "offset": {
                "year": year_offset,
                "month": month_offset,
                "day": day_offset,
                "hour": hour_offset,
                "minute": minute_offset,
                "second": second_offset,
            },
        },
    }


TOOLS: Dict[str, ToolSpec] = {
    "time": ToolSpec(
        name="time",
        description=(
            "获取服务器当前时间（精确到秒，含英文星期）。"
            " 支持 year/month/day/hour/minute/second 偏移（可为负数）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年偏移（可为负数）"},
                "month": {"type": "integer", "description": "月偏移（可为负数）"},
                "day": {"type": "integer", "description": "日偏移（可为负数）"},
                "hour": {"type": "integer", "description": "时偏移（可为负数）"},
                "minute": {"type": "integer", "description": "分偏移（可为负数）"},
                "second": {"type": "integer", "description": "秒偏移（可为负数）"},
            },
            "additionalProperties": False,
        },
        requires_confirmation=False,
        handler=_time,
    ),
}
