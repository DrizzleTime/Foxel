from datetime import date, datetime, time
from typing import Any


def clean_cell(value: Any) -> str:
    """单元格变成单行文本，竖线转义，避免拆开 Markdown 表格。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, datetime):
        text = value.isoformat(sep=" ")
    elif isinstance(value, date):
        text = value.isoformat()
    elif isinstance(value, time):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    return " ".join(text.split())


def markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    if width == 0:
        return ""
    normalized = [row + [""] * (width - len(row)) for row in rows]

    def line(row: list[str]) -> str:
        return "| " + " | ".join(row) + " |"

    header = normalized[0]
    separator = "| " + " | ".join("---" for _ in header) + " |"
    body = [line(row) for row in normalized[1:]]
    return "\n".join([line(header), separator, *body])
