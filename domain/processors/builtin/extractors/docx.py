import re
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .table import clean_cell, markdown_table
from .types import ExtractError, ExtractResult, Section


_HEADING_STYLE = re.compile(r"(?:heading|标题)\s*([1-6])$", re.IGNORECASE)


def _heading_level(paragraph: Paragraph) -> int | None:
    style = getattr(paragraph, "style", None)
    if style is None:
        return None
    for raw in (getattr(style, "style_id", None), getattr(style, "name", None)):
        if not raw:
            continue
        match = _HEADING_STYLE.search(str(raw).strip())
        if match:
            return int(match.group(1))
    return None


def _is_list_paragraph(paragraph: Paragraph) -> bool:
    p_pr = getattr(paragraph._p, "pPr", None)
    if p_pr is not None and getattr(p_pr, "numPr", None) is not None:
        return True
    style = getattr(paragraph, "style", None)
    name = str(getattr(style, "name", "") or "")
    return name.lower().startswith("list")


def _iter_blocks(document):
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _table_text(table: Table) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [clean_cell(cell.text) for cell in row.cells]
        if any(cells):
            rows.append(cells)
    return markdown_table(rows)


def extract_docx(data: bytes) -> ExtractResult:
    try:
        document = Document(BytesIO(data))
    except Exception as exc:
        raise ExtractError("文档无法解析") from exc

    lines: list[str] = []
    try:
        blocks = list(_iter_blocks(document))
    except Exception as exc:
        raise ExtractError("文档无法解析") from exc

    for block in blocks:
        if isinstance(block, Paragraph):
            text = " ".join(block.text.split())
            if not text:
                continue
            level = _heading_level(block)
            if level:
                lines.append(f"{'#' * level} {text}")
            elif _is_list_paragraph(block):
                lines.append(f"- {text}")
            else:
                lines.append(text)
            lines.append("")
            continue
        table_md = _table_text(block)
        if table_md:
            lines.append(table_md)
            lines.append("")

    text = "\n".join(lines).strip()
    if not text:
        raise ExtractError("文档没有可索引的文本")
    return ExtractResult(
        sections=[Section(heading="", text=text, kind="docx", locator={})],
        warnings=[],
    )
