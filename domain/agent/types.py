from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentChatContext(BaseModel):
    current_path: Optional[str] = None


class AgentChatRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    auto_execute: bool = False
    approved_tool_call_ids: List[str] = Field(default_factory=list)
    rejected_tool_call_ids: List[str] = Field(default_factory=list)
    context: Optional[AgentChatContext] = None


class PendingToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True

