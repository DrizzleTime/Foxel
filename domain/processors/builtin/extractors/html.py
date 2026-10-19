import re
from html.parser import HTMLParser

from .text import decode_bytes
from .types import ExtractError, ExtractResult, Section


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.heading_level = 0
        self.heading_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_heading()
            self.heading_level = int(tag[1])
            return
        if tag == "br":
            self.parts.append("\n")
        elif tag in {"p", "div", "section", "article", "tr", "table"}:
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            if self.skip:
                self.skip -= 1
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_heading()
        elif tag in {"p", "div", "li", "tr", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.heading_level:
            self.heading_buf.append(data)
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)
            self.parts.append(" ")

    def _flush_heading(self) -> None:
        if not self.heading_level:
            return
        title = " ".join("".join(self.heading_buf).split())
        if title:
            self.parts.append(f"\n{'#' * self.heading_level} {title}\n")
        self.heading_level = 0
        self.heading_buf = []

    def text(self) -> str:
        self._flush_heading()
        raw = "".join(self.parts)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def extract_html(data: bytes) -> ExtractResult:
    try:
        source = decode_bytes(data)
    except ExtractError:
        raise
    parser = _HTMLText()
    try:
        parser.feed(source)
        parser.close()
        text = parser.text()
    except Exception as exc:
        raise ExtractError("HTML 无法解析") from exc
    if not text:
        raise ExtractError("HTML 没有可索引的文本")
    return ExtractResult(
        sections=[Section(heading="", text=text, kind="html", locator={})],
        warnings=[],
    )
