from __future__ import annotations

import datetime
from typing import Dict

from tortoise.transactions import in_transaction

from core.version import VERSION
from models.database import (
    AutomationTask,
    Configuration,
    ShareLink,
    StorageAdapter,
    UserAccount,
)


class BackupService:
    async def export_data(self) -> Dict:
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

        return {
            "version": VERSION,
            "storage_adapters": list(adapters),
            "user_accounts": list(users),
            "automation_tasks": list(tasks),
            "share_links": list(shares),
            "configurations": list(configs),
        }

    async def import_data(self, data: dict):
        async with in_transaction() as conn:
            await ShareLink.all().using_db(conn).delete()
            await AutomationTask.all().using_db(conn).delete()
            await StorageAdapter.all().using_db(conn).delete()
            await UserAccount.all().using_db(conn).delete()
            await Configuration.all().using_db(conn).delete()

            if data.get("configurations"):
                await Configuration.bulk_create(
                    [Configuration(**c) for c in data["configurations"]], using_db=conn
                )

            if data.get("user_accounts"):
                await UserAccount.bulk_create(
                    [UserAccount(**u) for u in data["user_accounts"]], using_db=conn
                )

            if data.get("storage_adapters"):
                await StorageAdapter.bulk_create(
                    [StorageAdapter(**a) for a in data["storage_adapters"]],
                    using_db=conn,
                )

            if data.get("automation_tasks"):
                await AutomationTask.bulk_create(
                    [AutomationTask(**t) for t in data["automation_tasks"]],
                    using_db=conn,
                )

            if data.get("share_links"):
                await ShareLink.bulk_create(
                    [ShareLink(**s) for s in data["share_links"]], using_db=conn
                )


__all__ = ["BackupService"]
