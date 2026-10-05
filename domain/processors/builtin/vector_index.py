import base64
import mimetypes
import os
import re
from io import BytesIO
from typing import Dict, Any, List, NamedTuple, Tuple

from fastapi.responses import Response
from PIL import Image

from ..base import BaseProcessor
from domain.ai import (
    DEFAULT_VECTOR_DIMENSION,
    FILE_COLLECTION_NAME,
    VECTOR_COLLECTION_NAME,
    VectorDBService,
    describe_image_base64,
    get_text_embedding,
    provider_service,
)


# Qwen3-Embedding-8B 上下文是 32k。检索仍用远小于上下文的窗口，避免一篇文档收成一个向量。
# 非 ASCII 按 1 token 估算，ASCII 约 4 个字符 1 token。1500/2500 大约是原先 800 字窗口的两到三倍。
CHUNK_TARGET_TOKENS = 1500
CHUNK_MAX_TOKENS = 2500
CHUNK_MIN_TOKENS = 120
CHUNK_FORCE_OVERLAP_TOKENS = 150
MAX_IMAGE_EDGE = 1600
JPEG_QUALITY = 85

_HEADING_RE = re.compile(r"^( {0,3})(#{1,6})[ \t]+(\S.*?)[ \t]*$")
_FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
_FENCE_CLOSE_RE = re.compile(r"^( {0,3})(`+|~+)\s*$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$")
_CJK_SENTENCE_END = "。！？!?"


class TextChunk(NamedTuple):
    chunk_id: int
    text: str
    start: int
    end: int
    heading: str


class _Block(NamedTuple):
    start: int
    end: int
    kind: str
    heading: str


def _estimate_tokens(text: str) -> int:
    tokens = 0
    ascii_run = 0
    for char in text:
        if ord(char) < 128:
            ascii_run += 1
            continue
        if ascii_run:
            tokens += (ascii_run + 3) // 4
            ascii_run = 0
        tokens += 1
    if ascii_run:
        tokens += (ascii_run + 3) // 4
    return tokens


def _trim_span(content: str, start: int, end: int) -> Tuple[int, int, str]:
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return start, end, content[start:end]


def _iter_lines(content: str):
    start = 0
    length = len(content)
    while start < length:
        newline = content.find("\n", start)
        if newline == -1:
            raw_end = length - 1 if content.endswith("\r") else length
            yield start, length, content[start:raw_end]
            break
        raw_end = newline - 1 if newline > start and content[newline - 1] == "\r" else newline
        yield start, newline + 1, content[start:raw_end]
        start = newline + 1


def _heading_title(line: str) -> Tuple[int, str] | None:
    match = _HEADING_RE.match(line)
    if not match:
        return None
    title = re.sub(r"\s+#+\s*$", "", match.group(3)).strip()
    if not title:
        return None
    return len(match.group(2)), title


def _fence_open(line: str) -> Tuple[str, int] | None:
    match = _FENCE_OPEN_RE.match(line)
    if not match:
        return None
    token = match.group(2)
    return token[0], len(token)


def _fence_close(line: str, marker: str, minimum: int) -> bool:
    match = _FENCE_CLOSE_RE.match(line)
    if not match:
        return False
    token = match.group(2)
    return token[0] == marker and len(token) >= minimum


def _is_table_separator(line: str) -> bool:
    return _TABLE_SEP_RE.fullmatch(line.strip()) is not None


def _looks_like_table_start(lines, index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    current = lines[index][2]
    nxt = lines[index + 1][2]
    if "|" not in current and not _is_table_separator(current):
        return False
    return _is_table_separator(nxt) or (_is_table_separator(current) and "|" in nxt)


def _breadcrumb(stack: List[Tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack)


def _scan_blocks(content: str) -> List[_Block]:
    lines = list(_iter_lines(content))
    blocks: List[_Block] = []
    stack: List[Tuple[int, str]] = []
    index = 0
    while index < len(lines):
        start, end, raw = lines[index]
        fence = _fence_open(raw)
        if fence:
            marker, width = fence
            closing = index + 1
            while closing < len(lines):
                if _fence_close(lines[closing][2], marker, width):
                    closing += 1
                    break
                closing += 1
            blocks.append(_Block(start, lines[closing - 1][1], "code", _breadcrumb(stack)))
            index = closing
            continue

        heading = _heading_title(raw)
        if heading:
            level, title = heading
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            blocks.append(_Block(start, end, "heading", _breadcrumb(stack)))
            index += 1
            continue

        if not raw.strip():
            index += 1
            continue

        if _looks_like_table_start(lines, index):
            closing = index + 1
            while closing < len(lines) and lines[closing][2].strip() and "|" in lines[closing][2]:
                closing += 1
            blocks.append(_Block(start, lines[closing - 1][1], "table", _breadcrumb(stack)))
            index = closing
            continue

        closing = index + 1
        while closing < len(lines):
            current = lines[closing][2]
            if not current.strip() or _heading_title(current) or _fence_open(current):
                break
            if _looks_like_table_start(lines, closing):
                break
            closing += 1
        blocks.append(_Block(start, lines[closing - 1][1], "paragraph", _breadcrumb(stack)))
        index = closing
    return blocks


def _is_english_sentence_end(content: str, index: int, end: int) -> bool:
    if content[index] != "." or (index > 0 and content[index - 1].isdigit()):
        return False
    cursor = index + 1
    if cursor >= end:
        return True
    if not content[cursor].isspace():
        return False
    while cursor < end and content[cursor].isspace():
        cursor += 1
    if cursor >= end:
        return True
    return content[cursor].isascii() and content[cursor].isupper()


def _sentence_ranges(content: str, start: int, end: int) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    last = start
    for index in range(start, end):
        char = content[index]
        if char in _CJK_SENTENCE_END or _is_english_sentence_end(content, index, end):
            ranges.append((last, index + 1))
            last = index + 1
    if last < end:
        ranges.append((last, end))
    return [(left, right) for left, right in ranges if content[left:right].strip()]


def _fit_end(content: str, start: int, limit: int, max_tokens: int) -> int:
    if start >= limit:
        return limit
    low = start + 1
    high = limit
    best = min(limit, start + 1)
    while low <= high:
        mid = (low + high) // 2
        if _estimate_tokens(content[start:mid]) <= max_tokens:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    if best >= limit:
        return limit
    floor = start + max(1, int((best - start) * 0.8))
    snap = best
    for index in range(best - 1, floor - 1, -1):
        if content[index].isspace():
            snap = index
            break
    return max(snap, start + 1)


def _overlap_cursor(content: str, start: int, cut: int, overlap_tokens: int) -> int:
    if overlap_tokens <= 0 or cut - start <= 1:
        return cut
    low = start + 1
    high = cut
    answer = cut
    while low <= high:
        mid = (low + high) // 2
        if _estimate_tokens(content[mid:cut]) <= overlap_tokens:
            answer = mid
            high = mid - 1
        else:
            low = mid + 1
    if answer <= start or answer >= cut:
        return cut
    return answer


def _hard_windows(content: str, start: int, end: int, max_tokens: int, overlap_tokens: int) -> List[Tuple[int, int]]:
    windows: List[Tuple[int, int]] = []
    cursor = start
    while cursor < end:
        while cursor < end and content[cursor].isspace():
            cursor += 1
        if cursor >= end:
            break
        cut = _fit_end(content, cursor, end, max_tokens)
        if cut <= cursor:
            cut = min(end, cursor + 1)
        windows.append((cursor, cut))
        if cut >= end:
            break
        next_cursor = _overlap_cursor(content, cursor, cut, overlap_tokens)
        cursor = cut if next_cursor <= cursor or next_cursor >= cut else next_cursor
    return windows


def _line_pieces(content: str, start: int, end: int, max_tokens: int, overlap_tokens: int) -> List[Tuple[int, int]]:
    pieces: List[Tuple[int, int]] = []
    cursor = start
    while cursor < end:
        newline = content.find("\n", cursor, end)
        line_end = end if newline == -1 else newline + 1
        if _estimate_tokens(content[cursor:line_end]) > max_tokens:
            pieces.extend(_hard_windows(content, cursor, line_end, max_tokens, overlap_tokens))
        else:
            pieces.append((cursor, line_end))
        cursor = line_end
    return pieces


def _paragraph_pieces(content: str, start: int, end: int, max_tokens: int, overlap_tokens: int) -> List[Tuple[int, int]]:
    pieces: List[Tuple[int, int]] = []
    for left, right in _sentence_ranges(content, start, end):
        if _estimate_tokens(content[left:right]) > max_tokens:
            pieces.extend(_hard_windows(content, left, right, max_tokens, overlap_tokens))
        else:
            pieces.append((left, right))
    return pieces


def _section_pieces(content: str, blocks: List[_Block], max_tokens: int, overlap_tokens: int) -> List[Tuple[int, int]]:
    pieces: List[Tuple[int, int]] = []
    for block in blocks:
        if _estimate_tokens(content[block.start:block.end]) <= max_tokens:
            pieces.append((block.start, block.end))
        elif block.kind in ("code", "table"):
            pieces.extend(_line_pieces(content, block.start, block.end, max_tokens, overlap_tokens))
        elif block.kind == "paragraph":
            pieces.extend(_paragraph_pieces(content, block.start, block.end, max_tokens, overlap_tokens))
        else:
            pieces.extend(_hard_windows(content, block.start, block.end, max_tokens, overlap_tokens))
    return pieces


def _pack_pieces(content: str, pieces: List[Tuple[int, int]], heading: str, target_tokens: int, max_tokens: int, min_tokens: int) -> List[TextChunk]:
    chunks: List[TextChunk] = []
    buf_start = None
    buf_end = None
    buf_tokens = 0

    def flush() -> None:
        nonlocal buf_start, buf_end, buf_tokens
        if buf_start is None or buf_end is None:
            return
        start, end, text = _trim_span(content, buf_start, buf_end)
        buf_start = None
        buf_end = None
        buf_tokens = 0
        if text:
            chunks.append(TextChunk(0, text, start, end, heading))

    for raw_start, raw_end in pieces:
        start, end, text = _trim_span(content, raw_start, raw_end)
        if not text:
            continue
        if buf_start is not None and buf_end is not None:
            joined_tokens = _estimate_tokens(content[buf_start:end])
            over_target = joined_tokens > target_tokens and buf_tokens >= min_tokens
            if over_target or joined_tokens > max_tokens:
                flush()
        if buf_start is None:
            buf_start, buf_end = start, end
            buf_tokens = _estimate_tokens(text)
        else:
            buf_end = end
            buf_tokens = _estimate_tokens(content[buf_start:buf_end])
    flush()
    return chunks


def _merge_short(content: str, chunks: List[TextChunk], max_tokens: int, min_tokens: int) -> List[TextChunk]:
    if not chunks:
        return []
    merged: List[TextChunk] = [chunks[0]]
    for chunk in chunks[1:]:
        prev = merged[-1]
        if chunk.start < prev.end or content[prev.end:chunk.start].strip():
            merged.append(chunk)
            continue
        prev_tokens = _estimate_tokens(prev.text)
        cur_tokens = _estimate_tokens(chunk.text)
        if prev_tokens >= min_tokens and cur_tokens >= min_tokens:
            merged.append(chunk)
            continue
        if _estimate_tokens(content[prev.start:chunk.end]) > max_tokens:
            merged.append(chunk)
            continue
        start, end, text = _trim_span(content, prev.start, chunk.end)
        if prev_tokens < min_tokens and cur_tokens >= min_tokens:
            heading = chunk.heading or prev.heading
        else:
            heading = prev.heading or chunk.heading
        merged[-1] = TextChunk(0, text, start, end, heading)
    return [item._replace(chunk_id=index) for index, item in enumerate(merged)]


def _normalize_chunk_limits(target_tokens: int, max_tokens: int, min_tokens: int, overlap_tokens: int):
    max_tokens = max(int(max_tokens), 1)
    target_tokens = int(target_tokens)
    if target_tokens <= 0 or target_tokens > max_tokens:
        target_tokens = max_tokens
    min_tokens = max(int(min_tokens), 0)
    if min_tokens >= target_tokens:
        min_tokens = target_tokens // 4
    overlap_tokens = max(int(overlap_tokens), 0)
    if overlap_tokens >= max_tokens:
        overlap_tokens = max_tokens // 4
    return target_tokens, max_tokens, min_tokens, overlap_tokens


def _chunk_text(
    content: str,
    target_tokens: int = CHUNK_TARGET_TOKENS,
    max_tokens: int = CHUNK_MAX_TOKENS,
    min_tokens: int = CHUNK_MIN_TOKENS,
    overlap_tokens: int = CHUNK_FORCE_OVERLAP_TOKENS,
) -> List[TextChunk]:
    """按标题、段落和句子装箱。单块超过硬上限时，才用带重叠的字符窗口。"""
    target_tokens, max_tokens, min_tokens, overlap_tokens = _normalize_chunk_limits(
        target_tokens, max_tokens, min_tokens, overlap_tokens
    )
    blocks = _scan_blocks(content)
    preliminary: List[TextChunk] = []
    current_heading = None
    current_blocks: List[_Block] = []

    def flush_section() -> None:
        nonlocal current_blocks
        if not current_blocks:
            return
        pieces = _section_pieces(content, current_blocks, max_tokens, overlap_tokens)
        preliminary.extend(_pack_pieces(content, pieces, current_heading or "", target_tokens, max_tokens, min_tokens))
        current_blocks = []

    for block in blocks:
        if current_blocks and block.heading != current_heading:
            flush_section()
        current_heading = block.heading
        current_blocks.append(block)
    flush_section()
    return _merge_short(content, preliminary, max_tokens, min_tokens)


def _embed_text(path: str, heading: str, text: str) -> str:
    """embedding 输入带上文件名和标题路径，存进向量库的正文不含这段前缀。"""
    head = [os.path.basename(path) or path]
    if heading:
        head.append(heading)
    body = text.strip()
    prefix = "\n".join(head)
    if not body:
        return prefix
    return prefix + "\n\n" + body


def _guess_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _chunk_key(path: str, chunk_id: str) -> str:
    return f"{path}#chunk={chunk_id}"


def _compress_image_for_embedding(input_bytes: bytes) -> Tuple[bytes, Dict[str, Any] | None]:
    """压缩图片，降低发送到视觉模型的体积。"""
    if Image is None:
        return input_bytes, None

    try:
        with Image.open(BytesIO(input_bytes)) as img:
            img = img.convert("RGB")
            width, height = img.size
            longest_edge = max(width, height)
            scale = 1.0
            if longest_edge > MAX_IMAGE_EDGE:
                scale = MAX_IMAGE_EDGE / float(longest_edge)
                new_size = (max(int(width * scale), 1), max(int(height * scale), 1))
                resample_mode = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                img = img.resize(new_size, resample=resample_mode)

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            compressed = buffer.getvalue()

            if len(compressed) < len(input_bytes):
                return compressed, {
                    "original_bytes": len(input_bytes),
                    "compressed_bytes": len(compressed),
                    "scaled": scale < 1.0,
                    "width": img.width,
                    "height": img.height,
                }
    except Exception:  # pragma: no cover - 任意图像处理异常时回退
        return input_bytes, None

    return input_bytes, None


class VectorIndexProcessor:
    name = "向量索引"
    supported_exts: List[str] = []  # 留空表示不限扩展名
    config_schema = [
        {
            "key": "action", "label": "操作", "type": "select", "required": True, "default": "create",
            "options": [
                {"value": "create", "label": "创建索引"},
                {"value": "destroy", "label": "销毁索引"},
            ]
        },
        {
            "key": "index_type", "label": "索引类型", "type": "select", "required": True, "default": "vector",
            "options": [
                {"value": "vector", "label": "向量索引"},
                {"value": "simple", "label": "普通索引"},
            ]
        }
    ]
    produces_file = False
    requires_input_bytes = False

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]) -> Response:
        async def ensure_input_bytes() -> bytes:
            if input_bytes:
                return input_bytes
            from domain.virtual_fs import VirtualFSService
            return await VirtualFSService.read_file(path)

        action = config.get("action", "create")
        index_type = config.get("index_type", "vector")
        vector_db = VectorDBService()
        vector_collection = VECTOR_COLLECTION_NAME
        file_collection = FILE_COLLECTION_NAME

        if action == "destroy":
            target_collection = file_collection if index_type == "simple" else vector_collection
            await vector_db.delete_vector(target_collection, path)
            return Response(content=f"文件 {path} 的 {index_type} 索引已销毁", media_type="text/plain")

        mime_type = _guess_mime(path)

        if index_type == "simple":
            await vector_db.ensure_collection(file_collection, vector=False)
            await vector_db.delete_vector(file_collection, path)
            await vector_db.upsert_vector(file_collection, {
                "path": path,
                "source_path": path,
                "chunk_id": "filename",
                "mime": mime_type,
                "type": "filename",
                "name": os.path.basename(path),
            })
            return Response(content=f"文件 {path} 的普通索引已创建", media_type="text/plain")

        file_ext = path.split('.')[-1].lower()
        details: Dict[str, Any] = {"path": path, "action": "create", "index_type": "vector"}

        embedding_model = await provider_service.get_default_model("embedding")
        vector_dim = DEFAULT_VECTOR_DIMENSION
        if embedding_model and getattr(embedding_model, "embedding_dimensions", None):
            try:
                vector_dim = int(embedding_model.embedding_dimensions)
            except (TypeError, ValueError):
                vector_dim = DEFAULT_VECTOR_DIMENSION
            if vector_dim <= 0:
                vector_dim = DEFAULT_VECTOR_DIMENSION

        await vector_db.ensure_collection(vector_collection, vector=True, dim=vector_dim)
        await vector_db.delete_vector(vector_collection, path)

        if file_ext in ["jpg", "jpeg", "png", "bmp"]:
            file_bytes = await ensure_input_bytes()
            processed_bytes, compression = _compress_image_for_embedding(file_bytes)
            base64_image = base64.b64encode(processed_bytes).decode("utf-8")
            description = await describe_image_base64(base64_image)
            embedding = await get_text_embedding(description)
            image_mime = "image/jpeg" if compression else mime_type
            await vector_db.upsert_vector(vector_collection, {
                "path": _chunk_key(path, "image"),
                "source_path": path,
                "chunk_id": "image",
                "embedding": embedding,
                "text": description,
                "mime": image_mime,
                "type": "image",
            })
            details["description"] = description
            if compression:
                details["image_compression"] = compression
            return Response(content=f"图片已索引，描述：{description}", media_type="text/plain")

        if file_ext in ["txt", "md"]:
            try:
                file_bytes = await ensure_input_bytes()
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return Response(content="文本文件解码失败", status_code=400)

            chunks = _chunk_text(text)
            if not chunks:
                await vector_db.upsert_vector(vector_collection, {
                    "path": _chunk_key(path, "0"),
                    "source_path": path,
                    "chunk_id": "0",
                    "embedding": await get_text_embedding(_embed_text(path, "", text)),
                    "text": text,
                    "mime": mime_type,
                    "type": "text",
                    "start_offset": 0,
                    "end_offset": len(text),
                })
                details["chunks"] = 1
                return Response(content="文本文件已索引", media_type="text/plain")

            chunk_count = 0
            for chunk in chunks:
                payload = {
                    "path": _chunk_key(path, str(chunk.chunk_id)),
                    "source_path": path,
                    "chunk_id": str(chunk.chunk_id),
                    "embedding": await get_text_embedding(_embed_text(path, chunk.heading, chunk.text)),
                    "text": chunk.text,
                    "mime": mime_type,
                    "type": "text",
                    "start_offset": chunk.start,
                    "end_offset": chunk.end,
                }
                if chunk.heading:
                    payload["heading"] = chunk.heading
                await vector_db.upsert_vector(vector_collection, payload)
                chunk_count += 1

            details["chunks"] = chunk_count
            details["sample"] = chunks[0].text[:120]
            return Response(content="文本文件已索引", media_type="text/plain")

        # 其他类型暂未支持向量索引，回退为文件名索引
        await vector_db.ensure_collection(file_collection, vector=False)
        await vector_db.delete_vector(file_collection, path)
        await vector_db.upsert_vector(file_collection, {
            "path": path,
            "source_path": path,
            "chunk_id": "filename",
            "mime": mime_type,
            "type": "filename",
            "name": os.path.basename(path),
        })
        return Response(content="暂不支持该类型的向量索引，已创建文件名索引", media_type="text/plain")


PROCESSOR_TYPE = "vector_index"
PROCESSOR_NAME = VectorIndexProcessor.name
SUPPORTED_EXTS = VectorIndexProcessor.supported_exts
CONFIG_SCHEMA = VectorIndexProcessor.config_schema
def PROCESSOR_FACTORY(): return VectorIndexProcessor()
