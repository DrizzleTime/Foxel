from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from api.response import page
from domain.adapters import runtime_registry
from domain.ai import FILE_COLLECTION_NAME, VECTOR_COLLECTION_NAME, VectorDBService
from .thumbnail import is_image_filename, is_video_filename
from models import StorageAdapter

from .resolver import VirtualFSResolverMixin


class VirtualFSListingMixin(VirtualFSResolverMixin):
    @classmethod
    async def path_is_directory(cls, path: str) -> bool:
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        rel = rel.rstrip("/")
        if rel == "":
            return True
        stat_func = getattr(adapter_instance, "stat_file", None)
        if not callable(stat_func):
            raise HTTPException(501, detail="Adapter does not implement stat_file")
        try:
            info = await stat_func(root, rel)
        except FileNotFoundError:
            raise HTTPException(404, detail="Path not found")
        if isinstance(info, dict):
            return bool(info.get("is_dir"))
        return False

    @classmethod
    async def list_virtual_dir(
        cls,
        path: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Dict:
        norm = cls._normalize_path(path).rstrip("/") or "/"
        adapters = await StorageAdapter.filter(enabled=True)

        child_mount_entries: List[str] = []
        norm_prefix = norm.rstrip("/")
        for adapter in adapters:
            if adapter.path == norm:
                continue
            if adapter.path.startswith(norm_prefix + "/"):
                tail = adapter.path[len(norm_prefix) :].lstrip("/")
                if "/" not in tail:
                    child_mount_entries.append(tail)
        child_mount_entries = sorted(set(child_mount_entries))

        sort_field = sort_by.lower()
        reverse = sort_order.lower() == "desc"

        def build_sort_key(item: Dict) -> Tuple:
            key = (not bool(item.get("is_dir")),)
            if sort_field == "name":
                key += (str(item.get("name", "")).lower(),)
            elif sort_field == "size":
                key += (int(item.get("size", 0)),)
            elif sort_field == "mtime":
                key += (int(item.get("mtime", 0)),)
            else:
                key += (str(item.get("name", "")).lower(),)
            return key

        def annotate_entry(entry: Dict) -> None:
            if not entry.get("is_dir"):
                name = entry.get("name", "")
                entry["has_thumbnail"] = bool(is_image_filename(name) or is_video_filename(name))
            else:
                entry["has_thumbnail"] = False

        try:
            adapter_model, rel = await cls.resolve_adapter_by_path(norm)
            adapter_instance = runtime_registry.get(adapter_model.id)
            if not adapter_instance:
                await runtime_registry.refresh()
                adapter_instance = runtime_registry.get(adapter_model.id)

            if adapter_instance:
                effective_root = adapter_instance.get_effective_root(adapter_model.sub_path)
            else:
                adapter_model = None
                effective_root = ""
                rel = ""
        except HTTPException:
            adapter_model = None
            adapter_instance = None
            effective_root = ""
            rel = ""

        adapter_entries_for_merge: List[Dict] = []
        adapter_entries_page: List[Dict] | None = None
        adapter_total: int | None = None
        if adapter_model and adapter_instance:
            list_dir = getattr(adapter_instance, "list_dir", None)
            if callable(list_dir):
                adapter_entries_page, adapter_total = await list_dir(
                    effective_root, rel, page_num, page_size, sort_by, sort_order
                )
            if rel:
                parent_rel = cls._parent_rel(rel)
                if rel:
                    stat_file = getattr(adapter_instance, "stat_file", None)
                    if callable(stat_file):
                        try:
                            parent_info = await stat_file(effective_root, rel)
                            if isinstance(parent_info, dict):
                                parent_info.setdefault("name", rel.split("/")[-1])
                                parent_info["is_dir"] = bool(parent_info.get("is_dir", True))
                                adapter_entries_for_merge.append(parent_info)
                        except Exception:
                            pass
                if parent_rel:
                    stat_file = getattr(adapter_instance, "stat_file", None)
                    if callable(stat_file):
                        try:
                            parent_info = await stat_file(effective_root, parent_rel)
                            if isinstance(parent_info, dict):
                                parent_info.setdefault("name", parent_rel.split("/")[-1])
                                parent_info["is_dir"] = bool(parent_info.get("is_dir", True))
                                adapter_entries_for_merge.append(parent_info)
                        except Exception:
                            pass
            if adapter_entries_page:
                adapter_entries_for_merge.extend(adapter_entries_page)

        covered = set()
        if adapter_entries_for_merge:
            for item in adapter_entries_for_merge:
                covered.add(item["name"])

        mount_entries = []
        for name in child_mount_entries:
            if name not in covered:
                mount_entries.append(
                    {"name": name, "is_dir": True, "size": 0, "mtime": 0, "type": "mount", "has_thumbnail": False}
                )

        if mount_entries:
            for ent in adapter_entries_for_merge:
                annotate_entry(ent)
            combined_entries = adapter_entries_for_merge + [{**ent, "has_thumbnail": False} for ent in mount_entries]
            combined_entries.sort(key=build_sort_key, reverse=reverse)

            total_entries = len(combined_entries)
            start_idx = (page_num - 1) * page_size
            end_idx = start_idx + page_size
            page_entries = combined_entries[start_idx:end_idx]
            return page(page_entries, total_entries, page_num, page_size)

        annotate_entry_list = adapter_entries_page or []
        for ent in annotate_entry_list:
            annotate_entry(ent)
        return page(adapter_entries_page, adapter_total, page_num, page_size)

    @classmethod
    async def _gather_vector_index(cls, full_path: str, limit: int = 20):
        vector_db = VectorDBService()
        matched = []
        had_success = False
        fetch_limit = max(limit * 2, 20)
        for collection_name in (VECTOR_COLLECTION_NAME, FILE_COLLECTION_NAME):
            try:
                raw_results = await vector_db.search_by_path(collection_name, full_path, fetch_limit)
            except Exception:
                continue

            if not raw_results:
                had_success = True
                continue
            had_success = True
            buckets = raw_results if isinstance(raw_results, list) else [raw_results]
            for bucket in buckets:
                if not bucket:
                    continue
                for record in bucket:
                    entity = dict((record or {}).get("entity") or {})
                    source_path = entity.get("source_path") or entity.get("path") or ""
                    if source_path != full_path:
                        continue
                    entry = {
                        "chunk_id": str(entity.get("chunk_id")) if entity.get("chunk_id") is not None else None,
                        "type": entity.get("type"),
                        "mime": entity.get("mime"),
                        "name": entity.get("name"),
                        "start_offset": entity.get("start_offset"),
                        "end_offset": entity.get("end_offset"),
                        "vector_id": entity.get("vector_id"),
                    }
                    text = entity.get("text") or entity.get("description")
                    if text:
                        preview_limit = 400
                        entry["preview"] = text[:preview_limit]
                        entry["preview_truncated"] = len(text) > preview_limit
                    matched.append(entry)

        if not had_success:
            return None

        if not matched:
            return {"total": 0, "entries": [], "by_type": {}, "has_more": False}

        type_counts: Dict[str, int] = {}
        for item in matched:
            key = item.get("type") or "unknown"
            type_counts[key] = type_counts.get(key, 0) + 1

        has_more = len(matched) > limit
        return {
            "total": len(matched),
            "entries": matched[:limit],
            "by_type": type_counts,
            "has_more": has_more,
            "limit": limit,
        }

    @classmethod
    async def stat_file(cls, path: str):
        adapter_instance, _, root, rel = await cls.resolve_adapter_and_rel(path)
        stat_func = getattr(adapter_instance, "stat_file", None)
        if not callable(stat_func):
            raise HTTPException(501, detail="Adapter does not implement stat_file")
        info = await stat_func(root, rel)

        if isinstance(info, dict):
            info.setdefault("path", path)
            try:
                is_dir = bool(info.get("is_dir"))
            except Exception:
                is_dir = False
            rel_name = rel.rstrip("/").split("/")[-1] if rel else path.rstrip("/").split("/")[-1]
            name_hint = str(info.get("name") or rel_name or "")
            info["has_thumbnail"] = bool(not is_dir and (is_image_filename(name_hint) or is_video_filename(name_hint)))
            if not is_dir:
                vector_index = await cls._gather_vector_index(path)
                if vector_index is not None:
                    info["vector_index"] = vector_index

        return info
