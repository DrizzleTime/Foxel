from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ========== Manifest 相关类型 ==========


class ManifestFrontend(BaseModel):
    """manifest.json 中的 frontend 配置"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    entry: Optional[str] = Field(default=None, description="前端入口文件路径")
    open_app: Optional[bool] = Field(
        default=None,
        alias="openApp",
        description="是否支持独立打开",
    )
    supported_exts: Optional[List[str]] = Field(
        default=None,
        alias="supportedExts",
        description="支持的文件扩展名列表",
    )
    default_bounds: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="defaultBounds",
        description="默认窗口尺寸",
    )
    default_maximized: Optional[bool] = Field(
        default=None,
        alias="defaultMaximized",
        description="是否默认最大化",
    )
    icon: Optional[str] = Field(default=None, description="图标路径")


class ManifestRouteConfig(BaseModel):
    """manifest.json 中的路由配置"""

    model_config = ConfigDict(extra="ignore")

    module: str = Field(..., description="路由模块路径")
    prefix: str = Field(..., description="路由前缀")
    tags: Optional[List[str]] = Field(default=None, description="API 标签")


class ManifestProcessorConfig(BaseModel):
    """manifest.json 中的处理器配置"""

    model_config = ConfigDict(extra="ignore")

    module: str = Field(..., description="处理器模块路径")
    type: str = Field(..., description="处理器类型标识")
    name: Optional[str] = Field(default=None, description="处理器显示名称")


class ManifestBackend(BaseModel):
    """manifest.json 中的 backend 配置"""

    model_config = ConfigDict(extra="ignore")

    routes: Optional[List[ManifestRouteConfig]] = Field(default=None, description="路由列表")
    processors: Optional[List[ManifestProcessorConfig]] = Field(
        default=None, description="处理器列表"
    )


class ManifestDependencies(BaseModel):
    """manifest.json 中的依赖配置"""

    model_config = ConfigDict(extra="ignore")

    python: Optional[str] = Field(default=None, description="Python 版本要求")
    packages: Optional[List[str]] = Field(default=None, description="Python 包依赖列表")


class PluginManifest(BaseModel):
    """完整的 manifest.json 结构"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    foxpkg: str = Field(default="1.0", description="foxpkg 格式版本")
    key: str = Field(..., min_length=1, description="插件唯一标识")
    name: str = Field(..., min_length=1, description="插件名称")
    version: str = Field(default="1.0.0", description="插件版本")
    description: Optional[str] = Field(default=None, description="插件描述")
    author: Optional[str] = Field(default=None, description="作者")
    website: Optional[str] = Field(default=None, description="网站")
    github: Optional[str] = Field(default=None, description="GitHub 地址")
    license: Optional[str] = Field(default=None, description="许可证")

    frontend: Optional[ManifestFrontend] = Field(default=None, description="前端配置")
    backend: Optional[ManifestBackend] = Field(default=None, description="后端配置")
    dependencies: Optional[ManifestDependencies] = Field(default=None, description="依赖配置")


# ========== API 请求/响应类型 ==========


class PluginOut(BaseModel):
    """插件输出模型"""

    id: int
    key: str
    open_app: bool = False
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
    license: Optional[str] = None

    # 新增字段
    manifest: Optional[Dict[str, Any]] = None
    loaded_routes: Optional[List[str]] = None
    loaded_processors: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class PluginInstallResult(BaseModel):
    """安装结果"""

    success: bool
    plugin: Optional[PluginOut] = None
    message: Optional[str] = None
    errors: Optional[List[str]] = None
