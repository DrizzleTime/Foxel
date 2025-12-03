from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AIProviderEntity:
    id: int
    name: str
    identifier: str
    provider_type: Optional[str]
    api_format: str
    base_url: Optional[str]
    api_key: Optional[str]
    logo_url: Optional[str]
    extra_config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AIModelEntity:
    id: int
    provider_id: int
    name: str
    display_name: Optional[str]
    description: Optional[str]
    capabilities: List[str]
    context_window: Optional[int]
    embedding_dimensions: Optional[int]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    provider: Optional[AIProviderEntity] = None


@dataclass(frozen=True)
class AIDefaultModelEntity:
    ability: str
    model: Optional[AIModelEntity]


__all__ = ["AIProviderEntity", "AIModelEntity", "AIDefaultModelEntity"]
