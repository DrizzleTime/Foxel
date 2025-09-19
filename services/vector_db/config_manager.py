from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from services.config import ConfigCenter


class VectorDBConfigManager:
    TYPE_KEY = "VECTOR_DB_TYPE"
    CONFIG_KEY = "VECTOR_DB_CONFIG"
    DEFAULT_TYPE = "milvus_lite"

    @classmethod
    async def load_config(cls) -> Tuple[str, Dict[str, Any]]:
        raw_type = await ConfigCenter.get(cls.TYPE_KEY, cls.DEFAULT_TYPE)
        provider_type = str(raw_type or cls.DEFAULT_TYPE)

        raw_config = await ConfigCenter.get(cls.CONFIG_KEY)
        config_dict: Dict[str, Any] = {}
        if isinstance(raw_config, str) and raw_config:
            try:
                config_dict = json.loads(raw_config)
            except json.JSONDecodeError:
                config_dict = {}
        elif isinstance(raw_config, dict):
            config_dict = raw_config
        return provider_type, config_dict

    @classmethod
    async def save_config(cls, provider_type: str, config: Dict[str, Any]) -> None:
        await ConfigCenter.set(cls.TYPE_KEY, provider_type)
        await ConfigCenter.set(cls.CONFIG_KEY, json.dumps(config or {}))

    @classmethod
    async def get_type(cls) -> str:
        provider_type, _ = await cls.load_config()
        return provider_type

    @classmethod
    async def get_config(cls) -> Dict[str, Any]:
        _, config = await cls.load_config()
        return config
