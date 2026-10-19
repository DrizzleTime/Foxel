from typing import Any, NamedTuple


class Section(NamedTuple):
    heading: str
    text: str
    kind: str
    locator: dict[str, Any]


class ExtractResult(NamedTuple):
    sections: list[Section]
    warnings: list[str]


class ExtractError(Exception):
    """用户能看懂的提取失败。"""
