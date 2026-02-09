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
    ALL_SECTIONS = (
        "storage_adapters",
        "user_accounts",
        "automation_tasks",
        "share_links",
        "configurations",
        "ai_providers",
        "ai_models",
        "ai_default_models",
        "plugins",
    )

    @classmethod
    async def export_data(cls, sections: list[str] | None = None) -> BackupData:
        sections = cls._normalize_sections(sections)
        section_set = set(sections)
        async with in_transaction():
            adapters = (
                await StorageAdapter.all().values()
                if "storage_adapters" in section_set
                else []
            )
            users = (
                await UserAccount.all().values()
                if "user_accounts" in section_set
                else []
            )
            tasks = (
                await AutomationTask.all().values()
                if "automation_tasks" in section_set
                else []
            )
            shares = (
                await ShareLink.all().values()
                if "share_links" in section_set
                else []
            )
            configs = (
                await Configuration.all().values()
                if "configurations" in section_set
                else []
            )
            providers = (
                await AIProvider.all().values()
                if "ai_providers" in section_set
                else []
            )
            models = (
                await AIModel.all().values() if "ai_models" in section_set else []
            )
            default_models = (
                await AIDefaultModel.all().values()
                if "ai_default_models" in section_set
                else []
            )
            plugins = (
                await Plugin.all().values() if "plugins" in section_set else []
            )

        share_links = cls._serialize_datetime_fields(
            shares, ["created_at", "expires_at"]
        )
        user_accounts = cls._serialize_datetime_fields(
            users, ["created_at", "last_login"]
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
            sections=sections,
            storage_adapters=list(adapters),
            user_accounts=user_accounts,
            automation_tasks=list(tasks),
            share_links=share_links,
            configurations=list(configs),
            ai_providers=ai_providers,
            ai_models=ai_models,
            ai_default_models=ai_default_models,
            plugins=plugin_items,
        )

    @classmethod
    async def import_from_bytes(
        cls, filename: str, content: bytes, mode: str = "replace"
    ) -> None:
        if not filename.endswith(".json"):
            raise HTTPException(status_code=400, detail="无效的文件类型, 请上传 .json 文件")
        try:
            raw_data = json.loads(content)
        except Exception:
            raise HTTPException(status_code=400, detail="无法解析JSON文件")
        await cls.import_data(BackupData(**raw_data), mode=mode)

    @classmethod
    async def import_data(cls, payload: BackupData, mode: str = "replace") -> None:
        sections = cls._normalize_sections(payload.sections)
        if mode not in {"replace", "merge"}:
            raise HTTPException(status_code=400, detail="无效的导入模式")

        share_links = (
            cls._parse_datetime_fields(payload.share_links, ["created_at", "expires_at"])
            if payload.share_links
            else []
        )
        user_accounts = (
            cls._parse_datetime_fields(payload.user_accounts, ["created_at", "last_login"])
            if payload.user_accounts
            else []
        )
        ai_providers = (
            cls._parse_datetime_fields(payload.ai_providers, ["created_at", "updated_at"])
            if payload.ai_providers
            else []
        )
        ai_models = (
            cls._parse_datetime_fields(payload.ai_models, ["created_at", "updated_at"])
            if payload.ai_models
            else []
        )
        ai_default_models = (
            cls._parse_datetime_fields(
                payload.ai_default_models, ["created_at", "updated_at"]
            )
            if payload.ai_default_models
            else []
        )
        plugins = (
            cls._parse_datetime_fields(payload.plugins, ["created_at", "updated_at"])
            if payload.plugins
            else []
        )

        async with in_transaction() as conn:
            if mode == "replace":
                if "share_links" in sections:
                    await ShareLink.all().using_db(conn).delete()
                if "automation_tasks" in sections:
                    await AutomationTask.all().using_db(conn).delete()
                if "storage_adapters" in sections:
                    await StorageAdapter.all().using_db(conn).delete()
                if "user_accounts" in sections:
                    await UserAccount.all().using_db(conn).delete()
                if "configurations" in sections:
                    await Configuration.all().using_db(conn).delete()
                if "ai_default_models" in sections:
                    await AIDefaultModel.all().using_db(conn).delete()
                if "ai_models" in sections:
                    await AIModel.all().using_db(conn).delete()
                if "ai_providers" in sections:
                    await AIProvider.all().using_db(conn).delete()
                if "plugins" in sections:
                    await Plugin.all().using_db(conn).delete()

            if "configurations" in sections and payload.configurations:
                if mode == "merge":
                    await cls._merge_records(
                        Configuration, payload.configurations, conn
                    )
                else:
                    await Configuration.bulk_create(
                        [Configuration(**config) for config in payload.configurations],
                        using_db=conn,
                    )

            if "user_accounts" in sections and payload.user_accounts:
                if mode == "merge":
                    await cls._merge_records(UserAccount, user_accounts, conn)
                else:
                    await UserAccount.bulk_create(
                        [UserAccount(**user) for user in user_accounts],
                        using_db=conn,
                    )

            if "storage_adapters" in sections and payload.storage_adapters:
                if mode == "merge":
                    await cls._merge_records(
                        StorageAdapter, payload.storage_adapters, conn
                    )
                else:
                    await StorageAdapter.bulk_create(
                        [StorageAdapter(**adapter) for adapter in payload.storage_adapters],
                        using_db=conn,
                    )

            if "automation_tasks" in sections and payload.automation_tasks:
                if mode == "merge":
                    await cls._merge_records(
                        AutomationTask, payload.automation_tasks, conn
                    )
                else:
                    await AutomationTask.bulk_create(
                        [AutomationTask(**task) for task in payload.automation_tasks],
                        using_db=conn,
                    )

            if "share_links" in sections and share_links:
                if mode == "merge":
                    await cls._merge_records(ShareLink, share_links, conn)
                else:
                    await ShareLink.bulk_create(
                        [ShareLink(**share) for share in share_links],
                        using_db=conn,
                    )

            if "ai_providers" in sections and ai_providers:
                if mode == "merge":
                    await cls._merge_records(AIProvider, ai_providers, conn)
                else:
                    await AIProvider.bulk_create(
                        [AIProvider(**item) for item in ai_providers],
                        using_db=conn,
                    )

            if "ai_models" in sections and ai_models:
                if mode == "merge":
                    await cls._merge_records(AIModel, ai_models, conn)
                else:
                    await AIModel.bulk_create(
                        [AIModel(**item) for item in ai_models],
                        using_db=conn,
                    )

            if "ai_default_models" in sections and ai_default_models:
                if mode == "merge":
                    await cls._merge_records(
                        AIDefaultModel, ai_default_models, conn
                    )
                else:
                    await AIDefaultModel.bulk_create(
                        [AIDefaultModel(**item) for item in ai_default_models],
                        using_db=conn,
                    )

            if "plugins" in sections and plugins:
                if mode == "merge":
                    await cls._merge_records(Plugin, plugins, conn)
                else:
                    await Plugin.bulk_create(
                        [Plugin(**item) for item in plugins],
                        using_db=conn,
                    )

    @classmethod
    def _normalize_sections(cls, sections: list[str] | None) -> list[str]:
        if not sections:
            return list(cls.ALL_SECTIONS)
        normalized = [item for item in sections if item]
        invalid = [item for item in normalized if item not in cls.ALL_SECTIONS]
        if invalid:
            raise HTTPException(
                status_code=400, detail=f"无效的备份分区: {', '.join(invalid)}"
            )
        result: list[str] = []
        seen = set()
        for item in normalized:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    async def _merge_records(model, records: list[dict], using_db) -> None:
        for record in records:
            data = dict(record)
            record_id = data.pop("id", None)
            if record_id is None:
                await model.create(using_db=using_db, **data)
                continue
            updated = (
                await model.filter(id=record_id)
                .using_db(using_db)
                .update(**data)
            )
            if updated == 0:
                await model.create(using_db=using_db, id=record_id, **data)

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
