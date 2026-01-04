"""
视频库插件 API 路由

提供影视库的查询接口
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

DATA_ROOT = Path("data/.video")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_mtime_iso(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except FileNotFoundError:
        return ""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _extract_title(payload: Dict[str, Any]) -> str:
    detail = (payload.get("tmdb") or {}).get("detail") or {}
    if payload.get("type") == "tv":
        return str(detail.get("name") or detail.get("original_name") or "")
    return str(detail.get("title") or detail.get("original_title") or "")


def _extract_year(payload: Dict[str, Any]) -> Optional[str]:
    detail = (payload.get("tmdb") or {}).get("detail") or {}
    value = (
        detail.get("first_air_date")
        if payload.get("type") == "tv"
        else detail.get("release_date")
    )
    if not value or not isinstance(value, str):
        return None
    return value[:4] if len(value) >= 4 else value


def _extract_genres(payload: Dict[str, Any]) -> List[str]:
    detail = (payload.get("tmdb") or {}).get("detail") or {}
    genres = detail.get("genres") or []
    out: List[str] = []
    if isinstance(genres, list):
        for g in genres:
            if isinstance(g, dict) and g.get("name"):
                out.append(str(g["name"]))
    return out


def _summarize(item_id: str, payload: Dict[str, Any], mtime_iso: str) -> Dict[str, Any]:
    detail = (payload.get("tmdb") or {}).get("detail") or {}
    media_type = payload.get("type") or "unknown"
    episodes = payload.get("episodes") or []
    seasons = {
        e.get("season")
        for e in episodes
        if isinstance(e, dict) and e.get("season") is not None
    }

    return {
        "id": item_id,
        "type": media_type,
        "title": _extract_title(payload),
        "year": _extract_year(payload),
        "overview": detail.get("overview"),
        "poster_path": detail.get("poster_path"),
        "backdrop_path": detail.get("backdrop_path"),
        "genres": _extract_genres(payload),
        "tmdb_id": (payload.get("tmdb") or {}).get("id"),
        "source_path": payload.get("source_path"),
        "scraped_at": payload.get("scraped_at"),
        "updated_at": mtime_iso,
        "episodes_count": len(episodes) if isinstance(episodes, list) else 0,
        "seasons_count": len(seasons),
        "vote_average": detail.get("vote_average"),
        "vote_count": detail.get("vote_count"),
    }


def _iter_library_files() -> List[tuple[str, Path]]:
    files: List[tuple[str, Path]] = []
    for sub in ("tv", "movie"):
        folder = DATA_ROOT / sub
        if not folder.exists():
            continue
        for p in folder.glob("*.json"):
            if not p.is_file():
                continue
            files.append((sub, p))
    return files


@router.get("/library")
async def list_library(
    q: str | None = Query(None, description="搜索关键字（标题/简介）"),
    media_type: str | None = Query(None, alias="type", description="tv 或 movie"),
):
    """获取影视库列表"""
    items: List[Dict[str, Any]] = []
    keyword = (q or "").strip().lower()
    type_filter = (media_type or "").strip().lower()
    if type_filter and type_filter not in {"tv", "movie"}:
        raise HTTPException(status_code=400, detail="type must be tv or movie")

    for _sub, path in _iter_library_files():
        item_id = path.stem
        try:
            payload = _read_json(path)
        except Exception:
            continue
        if type_filter and str(payload.get("type") or "").lower() != type_filter:
            continue
        summary = _summarize(item_id, payload, _file_mtime_iso(path))
        if keyword:
            haystack = (
                f"{summary.get('title') or ''} {summary.get('overview') or ''}".lower()
            )
            if keyword not in haystack:
                continue
        items.append(summary)

    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return {"code": 0, "data": items}


@router.get("/library/{item_id}")
async def get_library_item(item_id: str):
    """获取单个影视条目详情"""
    candidates = [
        DATA_ROOT / "tv" / f"{item_id}.json",
        DATA_ROOT / "movie" / f"{item_id}.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        raise HTTPException(status_code=404, detail="Item not found")

    payload = _read_json(path)
    payload["id"] = item_id
    payload["updated_at"] = _file_mtime_iso(path)
    return {"code": 0, "data": payload}

