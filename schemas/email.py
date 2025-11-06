from typing import Any, Dict

from pydantic import BaseModel, EmailStr, Field


class EmailTestRequest(BaseModel):
    to: EmailStr
    subject: str = Field(..., min_length=1)
    template: str = Field(default="test", min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)


class EmailTemplateUpdate(BaseModel):
    content: str


class EmailTemplatePreviewPayload(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)
