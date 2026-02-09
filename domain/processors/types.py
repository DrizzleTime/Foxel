from typing import Any, Dict, Optional

from pydantic import BaseModel


class ProcessRequest(BaseModel):
    path: str
    processor_type: str
    config: Dict[str, Any]
    save_to: Optional[str] = None
    overwrite: bool = False


class ProcessDirectoryRequest(BaseModel):
    path: str
    processor_type: str
    config: Dict[str, Any]
    overwrite: bool = True
    max_depth: Optional[int] = None
    suffix: Optional[str] = None


class UpdateSourceRequest(BaseModel):
    source: str
