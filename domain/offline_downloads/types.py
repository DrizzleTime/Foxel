from pydantic import BaseModel, HttpUrl, Field


class OfflineDownloadCreate(BaseModel):
    url: HttpUrl
    dest_dir: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
