from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AutomationTaskBase(BaseModel):
    name: str
    event: str
    path_pattern: Optional[str] = None
    filename_regex: Optional[str] = None
    processor_type: str
    processor_config: Dict[str, Any] = {}
    enabled: bool = True


class AutomationTaskCreate(AutomationTaskBase):
    pass


class AutomationTaskUpdate(AutomationTaskBase):
    name: Optional[str] = None
    event: Optional[str] = None
    processor_type: Optional[str] = None
    processor_config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class AutomationTaskRead(AutomationTaskBase):
    id: int

    class Config:
        from_attributes = True


class TaskQueueSettings(BaseModel):
    concurrency: int = Field(..., ge=1, description="Desired number of concurrent task workers")


class TaskQueueSettingsResponse(TaskQueueSettings):
    active_workers: int = Field(..., ge=0, description="Currently running worker count")
