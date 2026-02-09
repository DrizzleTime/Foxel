import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, ValidationError


class EmailSecurity(str, Enum):
    NONE = "none"
    SSL = "ssl"
    STARTTLS = "starttls"


class EmailConfig(BaseModel):
    host: str
    port: int = Field(..., gt=0)
    username: Optional[str] = None
    password: Optional[str] = None
    sender_email: EmailStr
    sender_name: Optional[str] = None
    security: EmailSecurity = EmailSecurity.NONE
    timeout: float = Field(default=30.0, gt=0.0)

    @classmethod
    def parse_config(cls, raw_config: Any) -> "EmailConfig":
        """接受字符串或 dict 配置并解析为 EmailConfig。"""
        if raw_config is None:
            raise ValueError("Email configuration not found")

        if isinstance(raw_config, str):
            raw_config = raw_config.strip()
            data: Any = json.loads(raw_config) if raw_config else {}
        elif isinstance(raw_config, dict):
            data = raw_config
        else:
            raise ValueError("Invalid email configuration format")

        try:
            return cls(**data)
        except ValidationError as exc:
            raise ValueError(f"Invalid email configuration: {exc}") from exc


class EmailSendPayload(BaseModel):
    recipients: List[EmailStr] = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    template: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)


class EmailTestRequest(BaseModel):
    to: EmailStr
    subject: str = Field(..., min_length=1)
    template: str = Field(default="test", min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)


class EmailTemplateUpdate(BaseModel):
    content: str


class EmailTemplatePreviewPayload(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)
