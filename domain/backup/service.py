import json

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from domain.backup.types import BackupData
from domain.config.service import VERSION
from models.database import (
    AutomationTask,
    Configuration,
    ShareLink,
    StorageAdapter,
    UserAccount,
)


class BackupService:
    @classmethod
    async def export_data(cls) -> BackupData:
        async with in_transaction():
            adapters = await StorageAdapter.all().values()
            users = await UserAccount.all().values()
            tasks = await AutomationTask.all().values()
            shares = await ShareLink.all().values()
            configs = await Configuration.all().values()

        for share in shares:
            share["created_at"] = (
                share["created_at"].isoformat() if share.get("created_at") else None
            )
            share["expires_at"] = (
                share["expires_at"].isoformat() if share.get("expires_at") else None
            )

        return BackupData(
            version=VERSION,
            storage_adapters=list(adapters),
            user_accounts=list(users),
            automation_tasks=list(tasks),
            share_links=list(shares),
            configurations=list(configs),
        )

    @classmethod
    async def import_from_bytes(cls, filename: str, content: bytes) -> None:
        if not filename.endswith(".json"):
            raise HTTPException(status_code=400, detail="无效的文件类型, 请上传 .json 文件")
        try:
            raw_data = json.loads(content)
        except Exception:
            raise HTTPException(status_code=400, detail="无法解析JSON文件")
        await cls.import_data(BackupData(**raw_data))

    @classmethod
    async def import_data(cls, payload: BackupData) -> None:
        async with in_transaction() as conn:
            await ShareLink.all().using_db(conn).delete()
            await AutomationTask.all().using_db(conn).delete()
            await StorageAdapter.all().using_db(conn).delete()
            await UserAccount.all().using_db(conn).delete()
            await Configuration.all().using_db(conn).delete()

            if payload.configurations:
                await Configuration.bulk_create(
                    [Configuration(**config) for config in payload.configurations],
                    using_db=conn,
                )

            if payload.user_accounts:
                await UserAccount.bulk_create(
                    [UserAccount(**user) for user in payload.user_accounts],
                    using_db=conn,
                )

            if payload.storage_adapters:
                await StorageAdapter.bulk_create(
                    [StorageAdapter(**adapter) for adapter in payload.storage_adapters],
                    using_db=conn,
                )

            if payload.automation_tasks:
                await AutomationTask.bulk_create(
                    [AutomationTask(**task) for task in payload.automation_tasks],
                    using_db=conn,
                )

            if payload.share_links:
                await ShareLink.bulk_create(
                    [ShareLink(**share) for share in payload.share_links],
                    using_db=conn,
                )
