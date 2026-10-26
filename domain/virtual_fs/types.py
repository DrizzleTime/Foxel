from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from domain.permission.execution import ExecutionError, normalize_path


class VfsEntry(BaseModel):
    name: str
    is_dir: bool
    size: int
    mtime: int
    type: Optional[str] = None
    has_thumbnail: Optional[bool] = None


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


class BatchDeleteRequest(BaseModel):
    paths: List[str] = Field(min_length=1, max_length=200)

    @field_validator("paths", mode="after")
    @classmethod
    def normalize_paths(cls, value):
        try:
            return list(dict.fromkeys(normalize_path(path) for path in value))
        except ExecutionError as exc:
            raise ValueError("Invalid batch path") from exc


class BatchTransferRequest(BaseModel):
    srcs: List[str] = Field(min_length=1, max_length=200)
    dst: str

    @field_validator("srcs", "dst", mode="after")
    @classmethod
    def normalize_paths(cls, value):
        try:
            if isinstance(value, list):
                return list(dict.fromkeys(normalize_path(path) for path in value))
            return normalize_path(value)
        except ExecutionError as exc:
            raise ValueError("Invalid batch path") from exc


class CompressRequest(BaseModel):
    sources: List[str] = Field(min_length=1, max_length=1000)
    dst: str

    @field_validator("sources", "dst", mode="after")
    @classmethod
    def normalize_paths(cls, value):
        try:
            if isinstance(value, list):
                return list(dict.fromkeys(normalize_path(path) for path in value))
            return normalize_path(value)
        except ExecutionError as exc:
            raise ValueError("Invalid archive path") from exc


class ExtractRequest(BaseModel):
    src: str
    dst: str
    # Opt-in: if the task fails after creating destination paths, remove only those paths.
    cleanup_on_failure: bool = False

    @field_validator("src", "dst")
    @classmethod
    def normalize_paths(cls, value):
        try:
            return normalize_path(value)
        except ExecutionError as exc:
            raise ValueError("Invalid archive path") from exc
