from pydantic import BaseModel
from typing import List, Optional


class VfsEntry(BaseModel):
    name: str
    is_dir: bool
    size: int
    mtime: int
    type: Optional[str] = None
    is_image: Optional[bool] = None


class DirListing(BaseModel):
    path: str
    entries: List[VfsEntry]
    pagination: Optional[dict] = None


class SearchResultItem(BaseModel):
    id: int | str
    path: str
    score: float
    chunk_id: Optional[str] = None
    snippet: Optional[str] = None
    mime: Optional[str] = None
    source_type: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    metadata: Optional[dict] = None


class MkdirRequest(BaseModel):
    path: str


class MoveRequest(BaseModel):
    src: str
    dst: str
