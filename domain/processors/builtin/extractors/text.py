from .types import ExtractError, ExtractResult, Section


def decode_bytes(data: bytes) -> str:
    """先按 UTF-8（含 BOM）解码，失败再试 GBK。"""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractError("文本文件解码失败")


def extract_plain_text(data: bytes) -> ExtractResult:
    text = decode_bytes(data)
    return ExtractResult(
        sections=[Section(heading="", text=text, kind="text", locator={})],
        warnings=[],
    )
