import os

from .docx import extract_docx
from .html import extract_html
from .pdf import extract_pdf
from .pptx import extract_pptx
from .sheets import extract_csv, extract_xls, extract_xlsx
from .text import extract_plain_text
from .types import ExtractError, ExtractResult, Section


TEXT_EXTENSIONS = (
    "txt",
    "md",
    "markdown",
    "log",
    "json",
    "yaml",
    "yml",
    "xml",
    "ini",
    "cfg",
    "conf",
)

DOCUMENT_EXTENSIONS = (
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "xls",
    "csv",
    "html",
    "htm",
    *TEXT_EXTENSIONS,
)

_EXTRACTORS = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "pptx": extract_pptx,
    "xlsx": extract_xlsx,
    "xls": extract_xls,
    "html": extract_html,
    "htm": extract_html,
}


def extension_of(path: str) -> str:
    name = os.path.basename(path)
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def extract_document(path: str, data: bytes) -> ExtractResult:
    ext = extension_of(path)
    if ext in TEXT_EXTENSIONS:
        return extract_plain_text(data)
    if ext == "csv":
        stem = os.path.splitext(os.path.basename(path))[0] or "CSV"
        return extract_csv(data, stem)
    extractor = _EXTRACTORS.get(ext)
    if extractor is None:
        raise ExtractError("暂不支持该类型的向量索引")
    return extractor(data)


__all__ = [
    "DOCUMENT_EXTENSIONS",
    "TEXT_EXTENSIONS",
    "ExtractError",
    "ExtractResult",
    "Section",
    "extension_of",
    "extract_document",
]
