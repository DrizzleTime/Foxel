import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from domain.virtual_fs.service import VirtualFSService
from domain.virtual_fs.thumbnail import VIDEO_EXT, is_video_filename


DATA_ROOT = Path("data/.video")
TMDB_BASE_URL = "https://api.themoviedb.org/3"


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _store_path(media_type: str, source_path: str) -> Path:
    subdir = "tv" if media_type == "tv" else "movie"
    return DATA_ROOT / subdir / f"{_sha1(source_path)}.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


_CLEAN_TAGS_RE = re.compile(
    r"\b("
    r"2160p|1080p|720p|480p|4k|hdr|dv|dolby|atmos|"
    r"x264|x265|h264|h265|hevc|av1|aac|dts|flac|"
    r"bluray|bdrip|web[- ]?dl|webrip|dvdrip|remux|proper|repack"
    r")\b",
    re.IGNORECASE,
)


def _clean_query_name(raw: str) -> str:
    name = raw
    name = name.replace(".", " ").replace("_", " ")
    name = re.sub(r"\[[^\]]*\]", " ", name)
    name = re.sub(r"\([^\)]*\)", " ", name)
    name = _CLEAN_TAGS_RE.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _guess_name_from_path(path: str, is_dir: bool) -> str:
    norm = path.rstrip("/") if is_dir else path
    p = Path(norm)
    raw = p.name if is_dir else p.stem
    return _clean_query_name(raw)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
    return default


_SXXEYY_RE = re.compile(r"[Ss](\d{1,2})\s*[.\-_ ]*\s*[Ee](\d{1,3})")
_X_RE = re.compile(r"(\d{1,2})x(\d{1,3})", re.IGNORECASE)
_CN_EP_RE = re.compile(r"第\s*(\d{1,3})\s*[集话]")
_CN_SEASON_RE = re.compile(r"第\s*(\d{1,2})\s*季")
_SEASON_WORD_RE = re.compile(r"Season\s*(\d{1,2})", re.IGNORECASE)
_S_RE = re.compile(r"[Ss](\d{1,2})")


def _parse_season_episode(rel_path: str) -> Tuple[Optional[int], Optional[int]]:
    stem = Path(rel_path).stem

    m = _SXXEYY_RE.search(stem) or _SXXEYY_RE.search(rel_path)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = _X_RE.search(stem)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = _CN_EP_RE.search(stem)
    if m:
        episode = int(m.group(1))
        season = None
        for part in reversed(Path(rel_path).parts[:-1]):
            sm = _CN_SEASON_RE.search(part) or _SEASON_WORD_RE.search(part) or _S_RE.search(part)
            if sm:
                season = int(sm.group(1))
                break
        return season or 1, episode

    m = re.match(r"^(\d{1,3})(?!\d)", stem)
    if m:
        episode = int(m.group(1))
        season = None
        for part in reversed(Path(rel_path).parts[:-1]):
            sm = _CN_SEASON_RE.search(part) or _SEASON_WORD_RE.search(part) or _S_RE.search(part)
            if sm:
                season = int(sm.group(1))
                break
        return season or 1, episode

    return None, None


class TMDBClient:
    def __init__(self, access_token: str | None, api_key: str | None):
        self._access_token = access_token
        self._api_key = api_key

    @classmethod
    def from_env(cls) -> "TMDBClient":
        access_token = os.getenv("TMDB_ACCESS_TOKEN")
        api_key = os.getenv("TMDB_API_KEY")
        if not access_token and not api_key:
            raise RuntimeError("缺少 TMDB_ACCESS_TOKEN 或 TMDB_API_KEY")
        return cls(access_token=access_token, api_key=api_key)

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _merge_params(self, params: dict) -> dict:
        merged = dict(params or {})
        if self._api_key:
            merged.setdefault("api_key", self._api_key)
        return merged

    async def get(self, path: str, params: dict) -> dict:
        url = f"{TMDB_BASE_URL}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self._headers(), params=self._merge_params(params))
            resp.raise_for_status()
            return resp.json()


class VideoLibraryProcessor:
    name = "影视入库"
    supported_exts = sorted(VIDEO_EXT)
    config_schema = [
        {
            "key": "name",
            "label": "手动名称（可选）",
            "type": "string",
            "required": False,
            "placeholder": "留空则从路径提取",
        },
        {
            "key": "language",
            "label": "语言",
            "type": "string",
            "required": False,
            "default": "zh-CN",
        },
        {
            "key": "include_episodes",
            "label": "电视剧：保存每集",
            "type": "select",
            "required": False,
            "default": 1,
            "options": [
                {"label": "是", "value": 1},
                {"label": "否", "value": 0},
            ],
        },
    ]
    produces_file = False
    supports_directory = True
    requires_input_bytes = False

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]) -> Dict[str, Any]:
        tmdb = TMDBClient.from_env()
        is_dir = await VirtualFSService.path_is_directory(path)
        language = str(config.get("language") or "zh-CN")
        manual_name = str(config.get("name") or "").strip()
        query_name = manual_name or _guess_name_from_path(path, is_dir=is_dir)
        scraped_at = datetime.now(UTC).isoformat()

        if is_dir:
            payload, saved_to = await self._process_tv_dir(tmdb, path, query_name, language, scraped_at, config)
            return {
                "ok": True,
                "type": "tv",
                "path": path,
                "tmdb_id": payload.get("tmdb", {}).get("id"),
                "saved_to": str(saved_to),
            }

        payload, saved_to = await self._process_movie_file(tmdb, path, query_name, language, scraped_at)
        return {
            "ok": True,
            "type": "movie",
            "path": path,
            "tmdb_id": payload.get("tmdb", {}).get("id"),
            "saved_to": str(saved_to),
        }

    async def _process_movie_file(
        self,
        tmdb: TMDBClient,
        path: str,
        query_name: str,
        language: str,
        scraped_at: str,
    ) -> Tuple[dict, Path]:
        search = await tmdb.get("/search/movie", {"query": query_name, "language": language})
        results = search.get("results") or []
        if not results:
            raise RuntimeError(f"未找到电影条目：{query_name}")

        chosen = results[0] or {}
        movie_id = chosen.get("id")
        if not movie_id:
            raise RuntimeError("TMDB 搜索结果缺少 id")

        detail = await tmdb.get(
            f"/movie/{movie_id}",
            {
                "language": language,
                "append_to_response": "credits,images,external_ids,videos",
            },
        )

        payload = {
            "type": "movie",
            "source_path": path,
            "query": {"name": query_name, "language": language},
            "scraped_at": scraped_at,
            "tmdb": {
                "id": movie_id,
                "search": {"page": search.get("page"), "total_results": search.get("total_results"), "results": results[:5]},
                "detail": detail,
            },
        }
        saved_to = _store_path("movie", path)
        _write_json(saved_to, payload)
        return payload, saved_to

    async def _process_tv_dir(
        self,
        tmdb: TMDBClient,
        path: str,
        query_name: str,
        language: str,
        scraped_at: str,
        config: Dict[str, Any],
    ) -> Tuple[dict, Path]:
        search = await tmdb.get("/search/tv", {"query": query_name, "language": language})
        results = search.get("results") or []
        if not results:
            raise RuntimeError(f"未找到电视剧条目：{query_name}")

        chosen = results[0] or {}
        tv_id = chosen.get("id")
        if not tv_id:
            raise RuntimeError("TMDB 搜索结果缺少 id")

        detail = await tmdb.get(
            f"/tv/{tv_id}",
            {
                "language": language,
                "append_to_response": "credits,images,external_ids,videos",
            },
        )

        include_episodes = _as_bool(config.get("include_episodes"), True)
        episodes: List[dict] = []
        seasons_detail: Dict[str, Any] = {}
        if include_episodes:
            episodes = await self._collect_episode_files(path)
            seasons = sorted({ep["season"] for ep in episodes if ep.get("season") is not None})
            for season in seasons:
                seasons_detail[str(season)] = await tmdb.get(
                    f"/tv/{tv_id}/season/{int(season)}",
                    {"language": language},
                )
            self._attach_tmdb_episode_detail(episodes, seasons_detail)

        payload = {
            "type": "tv",
            "source_path": path,
            "query": {"name": query_name, "language": language},
            "scraped_at": scraped_at,
            "tmdb": {
                "id": tv_id,
                "search": {"page": search.get("page"), "total_results": search.get("total_results"), "results": results[:5]},
                "detail": detail,
                "seasons": seasons_detail,
            },
            "episodes": episodes,
        }

        saved_to = _store_path("tv", path)
        _write_json(saved_to, payload)
        return payload, saved_to

    async def _collect_episode_files(self, dir_path: str) -> List[dict]:
        adapter_instance, adapter_model, root, rel = await VirtualFSService.resolve_adapter_and_rel(dir_path)
        rel = rel.rstrip("/")
        list_dir = await VirtualFSService._ensure_method(adapter_instance, "list_dir")

        stack: List[str] = [rel]
        page_size = 200
        out: List[dict] = []

        while stack:
            current_rel = stack.pop()
            page = 1
            while True:
                entries, total = await list_dir(root, current_rel, page, page_size, "name", "asc")
                entries = entries or []
                if not entries and (total or 0) == 0:
                    break

                for entry in entries:
                    name = entry.get("name")
                    if not name:
                        continue
                    child_rel = VirtualFSService._join_rel(current_rel, name)
                    if entry.get("is_dir"):
                        stack.append(child_rel.rstrip("/"))
                        continue
                    if not is_video_filename(name):
                        continue

                    absolute_path = VirtualFSService._build_absolute_path(adapter_model.path, child_rel)
                    rel_in_show = child_rel
                    if rel and child_rel.startswith(rel.rstrip("/") + "/"):
                        rel_in_show = child_rel[len(rel.rstrip("/")) + 1 :]

                    season, episode = _parse_season_episode(rel_in_show)
                    out.append(
                        {
                            "path": absolute_path,
                            "rel": rel_in_show,
                            "name": name,
                            "size": entry.get("size"),
                            "mtime": entry.get("mtime"),
                            "season": season,
                            "episode": episode,
                        }
                    )

                if total is None or page * page_size >= total:
                    break
                page += 1

        return out

    def _attach_tmdb_episode_detail(self, episodes: List[dict], seasons_detail: Dict[str, Any]) -> None:
        episode_maps: Dict[str, Dict[int, Any]] = {}
        for season_str, season_payload in (seasons_detail or {}).items():
            items = (season_payload or {}).get("episodes") or []
            m: Dict[int, Any] = {}
            for item in items:
                try:
                    number = int(item.get("episode_number"))
                except Exception:
                    continue
                m[number] = item
            episode_maps[season_str] = m

        for ep in episodes:
            season = ep.get("season")
            episode = ep.get("episode")
            if season is None or episode is None:
                continue
            m = episode_maps.get(str(season))
            if not m:
                continue
            detail = m.get(int(episode))
            if detail:
                ep["tmdb_episode"] = detail


PROCESSOR_TYPE = "video_library"
PROCESSOR_NAME = VideoLibraryProcessor.name
SUPPORTED_EXTS = VideoLibraryProcessor.supported_exts
CONFIG_SCHEMA = VideoLibraryProcessor.config_schema
PROCESSOR_FACTORY = lambda: VideoLibraryProcessor()
