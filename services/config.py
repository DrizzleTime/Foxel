import os
from typing import Any, Optional, Dict

from dotenv import load_dotenv
from models.database import Configuration
load_dotenv(dotenv_path=".env")
VERSION = "v1.3.1"

class ConfigCenter:
    _cache: Dict[str, Any] = {}
    @classmethod
    async def get(cls, key: str, default: Optional[Any] = None) -> Any:
        if key in cls._cache:
            return cls._cache[key]
        try:
            config = await Configuration.get_or_none(key=key)
            if config:
                cls._cache[key] = config.value
                return config.value
        except Exception:
            pass
        env_value = os.getenv(key)
        if env_value is not None:
            cls._cache[key] = env_value
            return env_value
        return default

    @classmethod
    async def get_secret_key(cls, key: str, default: Optional[Any] = None) -> bytes:
        """获取密钥，确保返回的是bytes"""
        value = await cls.get(key, default)
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode('utf-8')
        if value is None:
            raise ValueError(f"Secret key '{key}' not found in config or environment.")
        return str(value).encode('utf-8')

    @classmethod
    async def set(cls, key: str, value: Any):
        obj, _ = await Configuration.get_or_create(key=key, defaults={"value": value})
        obj.value = value
        await obj.save()
        cls._cache[key] = value

    @classmethod
    async def get_all(cls) -> Dict[str, Any]:
        try:
            configs = await Configuration.all()
            result = {}
            for config in configs:
                result[config.key] = config.value
                cls._cache[config.key] = config.value
            return result
        except Exception:
            return {}

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
