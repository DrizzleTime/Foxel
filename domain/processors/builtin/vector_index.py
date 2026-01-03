import base64
import mimetypes
import os
from io import BytesIO
from typing import Dict, Any, List, Tuple

from fastapi.responses import Response
from PIL import Image

from ..base import BaseProcessor
from domain.ai.inference import describe_image_base64, get_text_embedding, provider_service
from domain.ai.service import (
    VectorDBService,
    DEFAULT_VECTOR_DIMENSION,
    VECTOR_COLLECTION_NAME,
    FILE_COLLECTION_NAME,
)


CHUNK_SIZE = 800
CHUNK_OVERLAP = 200
MAX_IMAGE_EDGE = 1600
JPEG_QUALITY = 85


def _chunk_text(content: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[Tuple[int, str, int, int]]:
    """按固定窗口拆分文本，返回(chunk_id, chunk_text, start, end)。"""
    if chunk_size <= 0:
        chunk_size = CHUNK_SIZE
    if overlap >= chunk_size:
        overlap = max(chunk_size // 4, 1)

    chunks: List[Tuple[int, str, int, int]] = []
    step = chunk_size - overlap
    idx = 0
    start = 0
    length = len(content)

    while start < length:
        end = min(length, start + chunk_size)
        chunk = content[start:end].strip()
        if chunk:
            chunks.append((idx, chunk, start, end))
            idx += 1
        if end >= length:
            break
        start += step
    return chunks


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

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]) -> Response:
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
            processed_bytes, compression = _compress_image_for_embedding(input_bytes)
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
                text = input_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return Response(content="文本文件解码失败", status_code=400)

            chunks = _chunk_text(text)
            if not chunks:
                await vector_db.upsert_vector(vector_collection, {
                    "path": _chunk_key(path, "0"),
                    "source_path": path,
                    "chunk_id": "0",
                    "embedding": await get_text_embedding(text or path),
                    "text": text,
                    "mime": mime_type,
                    "type": "text",
                    "start_offset": 0,
                    "end_offset": len(text),
                })
                details["chunks"] = 1
                return Response(content="文本文件已索引", media_type="text/plain")

            chunk_count = 0
            for chunk_id, chunk_text, start, end in chunks:
                embedding = await get_text_embedding(chunk_text)
                await vector_db.upsert_vector(vector_collection, {
                    "path": _chunk_key(path, str(chunk_id)),
                    "source_path": path,
                    "chunk_id": str(chunk_id),
                    "embedding": embedding,
                    "text": chunk_text,
                    "mime": mime_type,
                    "type": "text",
                    "start_offset": start,
                    "end_offset": end,
                })
                chunk_count += 1

            details["chunks"] = chunk_count
            sample = chunks[0][1]
            details["sample"] = sample[:120]
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
