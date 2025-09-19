from typing import Dict, Any
from fastapi.responses import Response
import base64
from services.ai import describe_image_base64, get_text_embedding
from services.vector_db import VectorDBService, DEFAULT_VECTOR_DIMENSION
from services.logging import LogService
from services.config import ConfigCenter


class VectorIndexProcessor:
    name = "向量索引"
    supported_exts = ["jpg", "jpeg", "png", "bmp", "txt", "md"]
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
        collection_name = "vector_collection"
        if action == "destroy":
            await vector_db.delete_vector(collection_name, path)
            await LogService.info(
                "processor:vector_index",
                f"Destroyed {index_type} index for {path}",
                details={"path": path, "action": "destroy", "index_type": index_type},
            )
            return Response(content=f"文件 {path} 的 {index_type} 索引已销毁", media_type="text/plain")

        if index_type == 'simple':
            await vector_db.ensure_collection(collection_name, vector=False)
            await vector_db.upsert_vector(collection_name, {'path': path})
            await LogService.info(
                "processor:vector_index",
                f"Created simple index for {path}",
                details={"path": path, "action": "create", "index_type": "simple"},
            )
            return Response(content=f"文件 {path} 的普通索引已创建", media_type="text/plain")

        file_ext = path.split('.')[-1].lower()
        description = ""
        embedding = None

        if file_ext in ["jpg", "jpeg", "png", "bmp"]:
            base64_image = base64.b64encode(input_bytes).decode("utf-8")
            description = await describe_image_base64(base64_image)
            embedding = await get_text_embedding(description)
            log_message = f"Indexed image {path}"
            response_message = f"图片已索引，描述：{description}"
        elif file_ext in ["txt", "md"]:
            text = input_bytes.decode("utf-8")
            embedding = await get_text_embedding(text)
            description = text[:100] + "..." if len(text) > 100 else text
            log_message = f"Indexed text file {path}"
            response_message = f"文本文件已索引"
        
        if embedding is None:
            return Response(content="不支持的文件类型", status_code=400)

        raw_dim = await ConfigCenter.get('AI_EMBED_DIM', DEFAULT_VECTOR_DIMENSION)
        try:
            vector_dim = int(raw_dim)
        except (TypeError, ValueError):
            vector_dim = DEFAULT_VECTOR_DIMENSION
        if vector_dim <= 0:
            vector_dim = DEFAULT_VECTOR_DIMENSION

        await vector_db.ensure_collection(collection_name, vector=True, dim=vector_dim)
        await vector_db.upsert_vector(
            collection_name, {'path': path, 'embedding': embedding})
        
        await LogService.info(
            "processor:vector_index",
            log_message,
            details={"path": path, "description": description, "action": "create", "index_type": "vector"},
        )
        return Response(content=response_message, media_type="text/plain")


PROCESSOR_TYPE = "vector_index"
PROCESSOR_NAME = VectorIndexProcessor.name
SUPPORTED_EXTS = VectorIndexProcessor.supported_exts
CONFIG_SCHEMA = VectorIndexProcessor.config_schema
def PROCESSOR_FACTORY(): return VectorIndexProcessor()
