import json
from datetime import datetime

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from domain.config import VERSION
from .types import BackupData
from models.database import (
    AIDefaultModel,
    AIModel,
    AIProvider,
    AutomationTask,
    Configuration,
    Plugin,
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
            providers = await AIProvider.all().values()
            models = await AIModel.all().values()
            default_models = await AIDefaultModel.all().values()
            plugins = await Plugin.all().values()

        share_links = cls._serialize_datetime_fields(
            shares, ["created_at", "expires_at"]
        )
        ai_providers = cls._serialize_datetime_fields(
            providers, ["created_at", "updated_at"]
        )
        ai_models = cls._serialize_datetime_fields(
            models, ["created_at", "updated_at"]
        )
        ai_default_models = cls._serialize_datetime_fields(
            default_models, ["created_at", "updated_at"]
        )
        plugin_items = cls._serialize_datetime_fields(
            plugins, ["created_at", "updated_at"]
        )

        return BackupData(
            version=VERSION,
            storage_adapters=list(adapters),
            user_accounts=list(users),
            automation_tasks=list(tasks),
            share_links=share_links,
            configurations=list(configs),
            ai_providers=ai_providers,
            ai_models=ai_models,
            ai_default_models=ai_default_models,
            plugins=plugin_items,
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
            await AIDefaultModel.all().using_db(conn).delete()
            await AIModel.all().using_db(conn).delete()
            await AIProvider.all().using_db(conn).delete()
            await Plugin.all().using_db(conn).delete()

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
                    [
                        ShareLink(**share)
                        for share in cls._parse_datetime_fields(
                            payload.share_links, ["created_at", "expires_at"]
                        )
                    ],
                    using_db=conn,
                )

            if payload.ai_providers:
                await AIProvider.bulk_create(
                    [
                        AIProvider(**item)
                        for item in cls._parse_datetime_fields(
                            payload.ai_providers, ["created_at", "updated_at"]
                        )
                    ],
                    using_db=conn,
                )

            if payload.ai_models:
                await AIModel.bulk_create(
                    [
                        AIModel(**item)
                        for item in cls._parse_datetime_fields(
                            payload.ai_models, ["created_at", "updated_at"]
                        )
                    ],
                    using_db=conn,
                )

            if payload.ai_default_models:
                await AIDefaultModel.bulk_create(
                    [
                        AIDefaultModel(**item)
                        for item in cls._parse_datetime_fields(
                            payload.ai_default_models, ["created_at", "updated_at"]
                        )
                    ],
                    using_db=conn,
                )

            if payload.plugins:
                await Plugin.bulk_create(
                    [
                        Plugin(**item)
                        for item in cls._parse_datetime_fields(
                            payload.plugins, ["created_at", "updated_at"]
                        )
                    ],
                    using_db=conn,
                )

    @staticmethod
    def _serialize_datetime_fields(
        records: list[dict], fields: list[str]
    ) -> list[dict]:
        serialized: list[dict] = []
        for record in records:
            item = dict(record)
            for field in fields:
                value = item.get(field)
                if isinstance(value, datetime):
                    item[field] = value.isoformat()
            serialized.append(item)
        return serialized

    @staticmethod
    def _parse_datetime_fields(
        records: list[dict], fields: list[str]
    ) -> list[dict]:
        parsed: list[dict] = []
        for record in records:
            item = dict(record)
            for field in fields:
                value = item.get(field)
                if isinstance(value, str):
                    item[field] = BackupService._from_iso(value)
            parsed.append(item)
        return parsed

    @staticmethod
    def _from_iso(value: str) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="无效的日期格式") from exc
