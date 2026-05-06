from pydantic import BaseModel, Field


class RecordRecentFileRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096, description="文件完整路径")


class RecentFileItem(BaseModel):
    id: int
    path: str
    opened_at: str
