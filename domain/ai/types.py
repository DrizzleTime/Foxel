from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field, field_validator

ABILITIES = ["chat", "vision", "embedding", "rerank", "voice", "tools"]
OPENAI_PROTOCOL_CHAT_COMPLETIONS = "chat_completions"
OPENAI_PROTOCOL_RESPONSES = "responses"
OPENAI_PROTOCOLS = {OPENAI_PROTOCOL_CHAT_COMPLETIONS, OPENAI_PROTOCOL_RESPONSES}
OPENAI_PROTOCOL_ALIASES = {
    "chat": OPENAI_PROTOCOL_CHAT_COMPLETIONS,
    "chat_completion": OPENAI_PROTOCOL_CHAT_COMPLETIONS,
    "chat_completions": OPENAI_PROTOCOL_CHAT_COMPLETIONS,
    "chat/completions": OPENAI_PROTOCOL_CHAT_COMPLETIONS,
    "/chat/completions": OPENAI_PROTOCOL_CHAT_COMPLETIONS,
    "response": OPENAI_PROTOCOL_RESPONSES,
    "responses": OPENAI_PROTOCOL_RESPONSES,
    "/responses": OPENAI_PROTOCOL_RESPONSES,
}


def normalize_capabilities(items: Optional[Iterable[str]]) -> List[str]:
    if not items:
        return []
    normalized: List[str] = []
    for cap in items:
        key = str(cap).strip().lower()
        if key in ABILITIES and key not in normalized:
            normalized.append(key)
    return normalized


def normalize_openai_protocol(value: Any) -> str:
    if value is None:
        return OPENAI_PROTOCOL_CHAT_COMPLETIONS
    key = str(value).strip().lower().replace("-", "_").replace(".", "_")
    if not key:
        return OPENAI_PROTOCOL_CHAT_COMPLETIONS
    normalized = OPENAI_PROTOCOL_ALIASES.get(key)
    if normalized:
        return normalized
    normalized = OPENAI_PROTOCOL_ALIASES.get(key.replace("_", "/"))
    if normalized:
        return normalized
    if key in OPENAI_PROTOCOLS:
        return key
    raise ValueError("openai_protocol must be 'chat_completions' or 'responses'")


def normalize_provider_extra_config(config: Optional[dict]) -> Optional[dict]:
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValueError("extra_config must be an object")
    normalized = dict(config)
    if "openai_protocol" in normalized:
        normalized["openai_protocol"] = normalize_openai_protocol(normalized.get("openai_protocol"))
    return normalized


class AIProviderBase(BaseModel):
    name: str
    identifier: str = Field(..., pattern=r"^[a-z0-9_\-\.]+$")
    provider_type: Optional[str] = None
    api_format: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    logo_url: Optional[str] = None
    extra_config: Optional[dict] = None

    @field_validator("api_format")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        fmt = value.lower()
        if fmt not in {"openai", "gemini", "anthropic", "ollama"}:
            raise ValueError("api_format must be 'openai', 'gemini', 'anthropic', or 'ollama'")
        return fmt

    @field_validator("extra_config")
    @classmethod
    def normalize_extra_config(cls, value: Optional[dict]) -> Optional[dict]:
        return normalize_provider_extra_config(value)


class AIProviderCreate(AIProviderBase):
    pass


class AIProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    api_format: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    logo_url: Optional[str] = None
    extra_config: Optional[dict] = None

    @field_validator("api_format")
    @classmethod
    def normalize_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        fmt = value.lower()
        if fmt not in {"openai", "gemini", "anthropic", "ollama"}:
            raise ValueError("api_format must be 'openai', 'gemini', 'anthropic', or 'ollama'")
        return fmt

    @field_validator("extra_config")
    @classmethod
    def normalize_extra_config(cls, value: Optional[dict]) -> Optional[dict]:
        return normalize_provider_extra_config(value)


class AIModelBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    context_window: Optional[int] = None
    embedding_dimensions: Optional[int] = None
    metadata: Optional[dict] = None

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, items: Optional[List[str]]) -> Optional[List[str]]:
        if items is None:
            return None
        normalized = normalize_capabilities(items)
        invalid = set(items) - set(normalized)
        if invalid:
            raise ValueError(f"Unsupported capabilities: {', '.join(invalid)}")
        return normalized


class AIModelCreate(AIModelBase):
    pass


class AIModelUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    context_window: Optional[int] = None
    embedding_dimensions: Optional[int] = None
    metadata: Optional[dict] = None

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, items: Optional[List[str]]) -> Optional[List[str]]:
        if items is None:
            return None
        normalized = normalize_capabilities(items)
        invalid = set(items) - set(normalized)
        if invalid:
            raise ValueError(f"Unsupported capabilities: {', '.join(invalid)}")
        return normalized


class AIDefaultsUpdate(BaseModel):
    chat: Optional[int] = None
    vision: Optional[int] = None
    embedding: Optional[int] = None
    rerank: Optional[int] = None
    voice: Optional[int] = None
    tools: Optional[int] = None

    def as_mapping(self) -> Dict[str, Optional[int]]:
        return {ability: getattr(self, ability) for ability in ABILITIES}


class VectorDBConfigPayload(BaseModel):
    type: str = Field(..., description="向量数据库提供者类型")
    config: Dict[str, Any] = Field(default_factory=dict, description="提供者配置参数")
