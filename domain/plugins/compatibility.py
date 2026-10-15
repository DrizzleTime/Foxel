"""Validate package and host requirements before executing plugin code."""
import platform
from importlib.metadata import PackageNotFoundError, version

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .loader import PluginLoadError
from .types import PluginManifest

HOST_API_VERSION = "1.0.0"


def check_compatibility(manifest: PluginManifest):
    try:
        if Version(manifest.foxpkg) != Version("1.0"):
            raise ValueError(f"不支持的 foxpkg 格式: {manifest.foxpkg}")
        Version(manifest.version)
        if Version(HOST_API_VERSION) not in SpecifierSet(manifest.host_api_version):
            raise ValueError(f"插件要求宿主 API {manifest.host_api_version}，当前为 {HOST_API_VERSION}")
        dependencies = manifest.dependencies
        if dependencies:
            if dependencies.python and Version(platform.python_version()) not in SpecifierSet(dependencies.python):
                raise ValueError(f"插件要求 Python {dependencies.python}，当前为 {platform.python_version()}")
            for value in dependencies.packages or []:
                requirement = Requirement(value)
                if requirement.marker and not requirement.marker.evaluate():
                    continue
                if requirement.url or requirement.extras:
                    raise ValueError(f"不支持自动验证 URL/extras 依赖: {value}")
                try:
                    installed = version(requirement.name)
                except PackageNotFoundError:
                    raise ValueError(f"缺少依赖: {requirement.name}")
                if Version(installed) not in requirement.specifier:
                    raise ValueError(f"依赖 {requirement.name} 要求 {requirement.specifier}，当前为 {installed}")
    except (ValueError, TypeError) as exc:
        raise PluginLoadError(f"兼容性检查失败: {exc}") from exc
