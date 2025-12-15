from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class PluginCreate(BaseModel):
    url: str = Field(min_length=1)
    enabled: bool = True


class PluginManifestUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    key: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    open_app: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("open_app", "openApp"),
    )
    supported_exts: Optional[List[str]] = Field(
        default=None,
        validation_alias=AliasChoices("supported_exts", "supportedExts"),
    )
    default_bounds: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("default_bounds", "defaultBounds"),
    )
    default_maximized: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("default_maximized", "defaultMaximized"),
    )
    icon: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None


class PluginOut(BaseModel):
    id: int
    url: str
    enabled: bool
    open_app: bool = False
    key: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    supported_exts: Optional[List[str]] = None
    default_bounds: Optional[Dict[str, Any]] = None
    default_maximized: Optional[bool] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
