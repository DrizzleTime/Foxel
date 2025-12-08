from typing import Any

from pydantic import BaseModel, Field


class BackupData(BaseModel):
    version: str | None = None
    storage_adapters: list[dict[str, Any]] = Field(default_factory=list)
    user_accounts: list[dict[str, Any]] = Field(default_factory=list)
    automation_tasks: list[dict[str, Any]] = Field(default_factory=list)
    share_links: list[dict[str, Any]] = Field(default_factory=list)
    configurations: list[dict[str, Any]] = Field(default_factory=list)
    ai_providers: list[dict[str, Any]] = Field(default_factory=list)
    ai_models: list[dict[str, Any]] = Field(default_factory=list)
    ai_default_models: list[dict[str, Any]] = Field(default_factory=list)
    plugins: list[dict[str, Any]] = Field(default_factory=list)
