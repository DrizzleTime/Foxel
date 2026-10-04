import json
import re
from typing import Dict, List


BUCKET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


def normalize_s3_base_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("S3 bucket base_path must be a string")
    value = value.strip()
    if "\\" in value or any(ord(char) < 32 for char in value):
        raise ValueError("S3 bucket base_path contains invalid characters")
    segments = [segment for segment in value.split("/") if segment]
    if any(segment in (".", "..") for segment in segments):
        raise ValueError("S3 bucket base_path cannot contain '.' or '..' segments")
    return "/" + "/".join(segments)


def parse_s3_bucket_mappings(raw: str) -> List[Dict[str, str]]:
    mappings = json.loads(raw)
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("S3 bucket mappings must be a non-empty array")
    result = []
    names = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("Each S3 bucket mapping must be an object")
        name = mapping.get("name")
        if not isinstance(name, str):
            raise ValueError("S3 bucket name must be a string")
        name = name.strip()
        if not BUCKET_NAME_RE.fullmatch(name):
            raise ValueError("S3 bucket name must contain 1-63 letters, digits, dots, underscores or hyphens and start with a letter or digit")
        if name in names:
            raise ValueError(f"Duplicate S3 bucket name: {name}")
        names.add(name)
        result.append({"name": name, "base_path": normalize_s3_base_path(mapping.get("base_path", "/"))})
    return result
