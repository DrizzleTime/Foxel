import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from domain.config import VERSION
from models.database import Notice

from .types import NoticeItem, NoticeListResponse

logger = logging.getLogger(__name__)

REMOTE_NOTICES_URL = "https://foxel.cc/api/notices"
SYNC_INTERVAL_SECONDS = 60 * 60 * 24
PAGE_SIZE = 20


def _normalize_version(version: str) -> str:
    return (version or "").strip().removeprefix("v").removeprefix("V")


def _parse_remote_time(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return datetime.now(timezone.utc)
        try:
            if text.isdigit():
                return _parse_remote_time(int(text))
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


class NoticeService:
    @classmethod
    async def list_notices(cls, page: int = 1, page_size: int = PAGE_SIZE) -> NoticeListResponse:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        query = Notice.all().order_by("-created_at", "-id")
        total = await query.count()
        notices = await query.offset((page - 1) * page_size).limit(page_size)
        return NoticeListResponse(
            items=[cls._to_item(item) for item in notices],
            page=page,
            pageSize=page_size,
            total=total,
        )

    @classmethod
    async def get_popup_notice(cls) -> NoticeItem | None:
        notice = await Notice.filter(is_popup=True, popup_dismissed=False).order_by("-created_at", "-id").first()
        if not notice:
            return None
        return cls._to_item(notice)

    @classmethod
    async def dismiss_popup(cls, notice_id: int) -> None:
        await Notice.filter(id=notice_id).update(popup_dismissed=True, is_popup=False)

    @classmethod
    async def sync_remote_notices(cls) -> None:
        items = await cls._fetch_remote_notices()
        if not items:
            return

        popup_remote_ids: list[int] = []
        for raw in items:
            remote_id = raw.get("id")
            if remote_id is None:
                continue
            try:
                remote_id = int(remote_id)
            except (TypeError, ValueError):
                continue

            is_popup = bool(raw.get("isPopup"))
            if is_popup:
                popup_remote_ids.append(remote_id)

            notice = await Notice.get_or_none(remote_id=remote_id)
            popup_dismissed = notice.popup_dismissed if notice else False
            await Notice.update_or_create(
                remote_id=remote_id,
                defaults={
                    "title": str(raw.get("title") or "")[:255],
                    "content_md": str(raw.get("contentMd") or ""),
                    "is_popup": is_popup and not popup_dismissed,
                    "created_at": _parse_remote_time(raw.get("createdAt")),
                },
            )

        await cls._keep_only_latest_popup(popup_remote_ids)

    @classmethod
    async def _keep_only_latest_popup(cls, popup_remote_ids: list[int]) -> None:
        latest = await Notice.filter(remote_id__in=popup_remote_ids, popup_dismissed=False).order_by(
            "-created_at", "-id"
        ).first()
        if not latest:
            return
        await Notice.filter(is_popup=True).exclude(id=latest.id).update(is_popup=False)

    @classmethod
    async def _fetch_remote_notices(cls) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            while True:
                resp = await client.get(
                    REMOTE_NOTICES_URL,
                    params={"version": _normalize_version(VERSION), "page": page},
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items") if isinstance(data, dict) else None
                if not isinstance(items, list):
                    break
                results.extend(item for item in items if isinstance(item, dict))

                total = data.get("total", len(results)) if isinstance(data, dict) else len(results)
                page_size = data.get("pageSize") or data.get("page_size") or len(items)
                if not items or len(results) >= int(total or 0) or page_size <= 0:
                    break
                page += 1
        return results

    @staticmethod
    def _to_item(notice: Notice) -> NoticeItem:
        return NoticeItem(
            id=notice.id,
            title=notice.title,
            contentMd=notice.content_md or "",
            isPopup=notice.is_popup and not notice.popup_dismissed,
            createdAt=int(notice.created_at.timestamp() * 1000),
        )


class NoticeSyncService:
    def __init__(self):
        self._worker: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._worker and not self._worker.done():
            return
        self._stop_event.clear()
        self._worker = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._worker:
            return
        self._stop_event.set()
        await self._worker
        self._worker = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await NoticeService.sync_remote_notices()
            except Exception:
                logger.exception("Failed to sync notices")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=SYNC_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass


notice_sync_service = NoticeSyncService()
