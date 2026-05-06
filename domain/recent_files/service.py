from datetime import datetime, timezone

from models.database import RecentFile


class RecentFilesService:
    @staticmethod
    async def record_opened_file(user_id: int, path: str) -> dict:
        item, created = await RecentFile.get_or_create(user_id=user_id, path=path)
        if not created:
            await RecentFile.filter(id=item.id).update(opened_at=datetime.now(timezone.utc))
            await item.fetch_from_db()
        return {"id": item.id, "path": item.path, "opened_at": item.opened_at.isoformat()}

    @staticmethod
    async def list_recent_files(user_id: int, limit: int) -> list[dict]:
        items = await RecentFile.filter(user_id=user_id).order_by("-opened_at").limit(limit)
        return [{"id": i.id, "path": i.path, "opened_at": i.opened_at.isoformat()} for i in items]

    @staticmethod
    async def clear_recent_files(user_id: int) -> dict:
        deleted = await RecentFile.filter(user_id=user_id).delete()
        return {"deleted": deleted}
