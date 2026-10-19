"""文件名和正文的 SQLite FTS5 索引。

向量库有 Milvus Lite、Milvus Server、Qdrant 三种，不把 BM25 绑在其中任何一种上。
无空格文字先切成重叠二字，再交给 unicode61，否则整段中文会被当成一个词。
"""

import asyncio
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

_DB_PATH = Path("data/db/lexical.sqlite")
_BM25_WEIGHTS = (3.0, 1.5, 1.0, 0.5)  # name, heading, body, path。bm25() 越小越好。
_UNSPACED = (
    "\u3040-\u30ff"  # 平假名、片假名
    "\u31f0-\u31ff"  # 片假名语音扩展
    "\u3400-\u9fff"  # 中日韩统一表意文字
    "\uf900-\ufaff"  # 兼容表意文字
    "\uac00-\ud7af"  # 谚文音节
)
_RUN_RE = re.compile(rf"[A-Za-z0-9][A-Za-z0-9_\-]*|[{_UNSPACED}]+")

_INSERT = """
INSERT INTO chunks (
    name, heading, body, path,
    source_path, chunk_id, snippet, display_heading,
    mime, kind, page, sheet, slide
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


@dataclass(frozen=True)
class LexicalChunk:
    source_path: str
    chunk_id: str
    name: str
    heading: str
    text: str
    mime: str = ""
    kind: str = ""
    page: int | None = None
    sheet: str | None = None
    slide: int | None = None


@dataclass(frozen=True)
class LexicalHit:
    source_path: str
    chunk_id: str
    snippet: str
    heading: str
    mime: str
    kind: str
    page: int | None
    sheet: str | None
    slide: int | None
    score: float


def tokenize(text: str) -> list[str]:
    """ASCII 词保持完整并小写；连续无空格文字切成重叠二字，单字保持单字。"""
    tokens: list[str] = []
    for match in _RUN_RE.finditer(text or ""):
        run = match.group(0)
        if run[0].isascii():
            tokens.append(run.lower())
            continue
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def fts_token(token: str) -> str:
    """unicode61 会把连字符和下划线当分隔符，先折进词里，查询和入库用同一规则。"""
    if not token:
        return ""
    if token.isascii():
        return token.replace("-", "").replace("_", "")
    return token


def build_match_query(text: str) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()
    for token in tokenize(text):
        normalized = fts_token(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        escaped = normalized.replace('"', '""')
        parts.append(f'"{escaped}"')
        if normalized.isascii() and len(normalized) >= 3:
            parts.append(f'"{escaped}"*')
    if not parts:
        return None
    return " OR ".join(parts)


def _indexed(text: str) -> str:
    return " ".join(token for token in (fts_token(raw) for raw in tokenize(text)) if token)


def _optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hit_from_row(row, matched_text: bool, score: float | None = None) -> LexicalHit:
    return LexicalHit(
        source_path=row["source_path"] or "",
        chunk_id=str(row["chunk_id"] or ""),
        snippet=(row["snippet"] or "") if matched_text else "",
        heading=(row["display_heading"] or "") if matched_text else "",
        mime=row["mime"] or "",
        kind=row["kind"] or "",
        page=_optional_int(row["page"]) if matched_text else None,
        sheet=_optional_str(row["sheet"]) if matched_text else None,
        slide=_optional_int(row["slide"]) if matched_text else None,
        score=float(row["score"]) if score is None else score,
    )


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


class LexicalIndex:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _DB_PATH
        self._ready = False
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        with self._lock:
            if not self._ready:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                        name,
                        heading,
                        body,
                        path,
                        source_path UNINDEXED,
                        chunk_id UNINDEXED,
                        snippet UNINDEXED,
                        display_heading UNINDEXED,
                        mime UNINDEXED,
                        kind UNINDEXED,
                        page UNINDEXED,
                        sheet UNINDEXED,
                        slide UNINDEXED,
                        tokenize = 'unicode61'
                    )
                    """
                )
                self._ready = True
        return conn

    def _row(self, chunk: LexicalChunk) -> tuple:
        return (
            _indexed(chunk.name),
            _indexed(chunk.heading),
            _indexed(chunk.text),
            _indexed(chunk.source_path),
            chunk.source_path,
            str(chunk.chunk_id),
            chunk.text or "",
            chunk.heading or "",
            chunk.mime or "",
            chunk.kind or "",
            chunk.page,
            chunk.sheet or None,
            chunk.slide,
        )

    def _replace_content_sync(self, source_path: str, chunks: list[LexicalChunk]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE source_path = ?", (source_path,))
            conn.executemany(_INSERT, [self._row(chunk) for chunk in chunks])

    def _replace_filename_sync(self, chunk: LexicalChunk) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM chunks WHERE source_path = ? AND chunk_id = 'filename'",
                (chunk.source_path,),
            )
            conn.execute(_INSERT, self._row(chunk))

    def _delete_sync(self, source_path: str, clause: str, params: tuple) -> None:
        with self._connect() as conn:
            conn.execute(f"DELETE FROM chunks WHERE source_path = ? AND {clause}", (source_path, *params))

    def _search_sync(self, query: str, limit: int) -> list[LexicalHit]:
        match = build_match_query(query)
        if not match or limit <= 0:
            return []
        sql_limit = min(max(limit, 1) * 8, 400)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_path, chunk_id, snippet, display_heading, mime, kind, page, sheet, slide,
                       bm25(chunks, ?, ?, ?, ?) AS score,
                       bm25(chunks, 0.0, ?, ?, 0.0) AS content_score
                FROM chunks
                WHERE chunks MATCH ?
                ORDER BY score ASC
                LIMIT ?
                """,
                (*_BM25_WEIGHTS, _BM25_WEIGHTS[1], _BM25_WEIGHTS[2], match, sql_limit),
            ).fetchall()
        # 文件名写在每个分块上，最短的一块往往会在 BM25 里压过真正命中正文的块。
        # 文件排序仍用最好的总分；摘要优先取标题或正文命中的块。
        ordered: list[str] = []
        chosen: dict[str, LexicalHit] = {}
        has_content: dict[str, bool] = {}
        for row in rows:
            path = row["source_path"] or ""
            if not path:
                continue
            content = float(row["content_score"] or 0.0)
            matched_text = content < 0
            if path not in chosen:
                if len(chosen) >= limit:
                    continue
                chosen[path] = _hit_from_row(row, matched_text)
                has_content[path] = matched_text
                ordered.append(path)
                continue
            if not has_content[path] and matched_text:
                chosen[path] = _hit_from_row(row, True, score=chosen[path].score)
                has_content[path] = True
        return [chosen[path] for path in ordered]

    async def replace_content(self, source_path: str, chunks: list[LexicalChunk]) -> None:
        await asyncio.to_thread(self._replace_content_sync, source_path, chunks)

    async def replace_filename(self, chunk: LexicalChunk) -> None:
        await asyncio.to_thread(self._replace_filename_sync, chunk)

    async def delete_all(self, source_path: str) -> None:
        await asyncio.to_thread(self._delete_sync, source_path, "1 = 1", ())

    async def delete_content(self, source_path: str) -> None:
        await asyncio.to_thread(self._delete_sync, source_path, "chunk_id != ?", ("filename",))

    async def delete_filename(self, source_path: str) -> None:
        await asyncio.to_thread(self._delete_sync, source_path, "chunk_id = ?", ("filename",))

    async def search(self, query: str, limit: int) -> list[LexicalHit]:
        return await asyncio.to_thread(self._search_sync, query, limit)


_index: LexicalIndex | None = None
_index_lock = threading.Lock()


def get_lexical_index() -> LexicalIndex:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = LexicalIndex()
    return _index
