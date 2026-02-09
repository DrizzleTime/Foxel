from typing import Any, Optional

from pydantic import BaseModel


class ConfigItem(BaseModel):
    key: str
    value: Optional[Any] = None


class SystemStatus(BaseModel):
    version: str
    title: str
    logo: str
    favicon: str
    is_initialized: bool
    app_domain: Optional[str] = None
    file_domain: Optional[str] = None


class LatestVersionInfo(BaseModel):
    latest_version: Optional[str] = None
    body: Optional[str] = None
