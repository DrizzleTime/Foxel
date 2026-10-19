from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .types import ExtractError, ExtractResult, Section


def extract_pdf(data: bytes) -> ExtractResult:
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, ValueError, OSError) as exc:
        raise ExtractError("PDF 无法解析") from exc

    if reader.is_encrypted:
        try:
            decrypted = reader.decrypt("")
        except Exception as exc:
            raise ExtractError("PDF 已加密，无法提取文本") from exc
        if not decrypted:
            raise ExtractError("PDF 已加密，无法提取文本")

    sections: list[Section] = []
    try:
        pages = reader.pages
    except Exception as exc:
        raise ExtractError("PDF 无法解析") from exc

    for index, page in enumerate(pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as exc:
            raise ExtractError("PDF 无法解析") from exc
        text = raw.strip()
        if not text:
            continue
        sections.append(Section(
            heading=f"第 {index} 页",
            text=text,
            kind="pdf",
            locator={"page": index},
        ))

    if not sections:
        raise ExtractError("该 PDF 没有可提取的文字层，暂不支持扫描件")
    return ExtractResult(sections=sections, warnings=[])
