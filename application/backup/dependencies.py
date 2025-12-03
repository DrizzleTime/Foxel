from __future__ import annotations

from application.backup.use_cases import BackupService

backup_service = BackupService()

__all__ = ["backup_service"]
