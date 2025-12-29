import os
import time
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from domain.config.types import LatestVersionInfo, SystemStatus
from models.database import Configuration, UserAccount

load_dotenv(dotenv_path=".env")

VERSION = "v1.5.1"


class ConfigService:
    _cache: Dict[str, Any] = {}
    _latest_version_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}

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
        value = await cls.get(key, default)
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        if value is None:
            raise ValueError(f"Secret key '{key}' not found in config or environment.")
        return str(value).encode("utf-8")

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

    @classmethod
    async def get_system_status(cls) -> SystemStatus:
        logo = await cls.get("APP_LOGO", "/logo.svg")
        favicon = await cls.get("APP_FAVICON", logo)
        user_count = await UserAccount.all().count()
        return SystemStatus(
            version=VERSION,
            title=await cls.get("APP_NAME", "Foxel"),
            logo=logo,
            favicon=favicon,
            is_initialized=user_count > 0,
            app_domain=await cls.get("APP_DOMAIN"),
            file_domain=await cls.get("FILE_DOMAIN"),
        )

    @classmethod
    async def get_latest_version(cls) -> LatestVersionInfo:
        current_time = time.time()
        cache = cls._latest_version_cache
        if current_time - cache["timestamp"] < 3600 and cache["data"]:
            return cache["data"]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.github.com/repos/DrizzleTime/Foxel/releases/latest",
                    follow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.json()
                version_info = LatestVersionInfo(
                    latest_version=data.get("tag_name"),
                    body=data.get("body"),
                )
                cache["timestamp"] = current_time
                cache["data"] = version_info
                return version_info
        except httpx.RequestError:
            if cache["data"]:
                return cache["data"]
            return LatestVersionInfo()
