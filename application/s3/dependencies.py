from __future__ import annotations

from application.s3.use_cases import S3MappingService

s3_mapping_service = S3MappingService()

__all__ = ["s3_mapping_service"]
