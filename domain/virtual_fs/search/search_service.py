from typing import Any, Dict, List, Tuple

from domain.ai import FILE_COLLECTION_NAME, VECTOR_COLLECTION_NAME, VectorDBService, get_text_embedding
from ..types import SearchResultItem


def _normalize_result(raw: Dict[str, Any], source: str, fallback_score: float = 0.0) -> SearchResultItem:
    entity = dict(raw.get("entity") or {})
    source_path = entity.get("source_path")
    stored_path = entity.get("path")
    path = source_path or stored_path or ""
    chunk_id_value = entity.get("chunk_id")
    chunk_id = str(chunk_id_value) if chunk_id_value is not None else None
    snippet = entity.get("text") or entity.get("description") or entity.get("name")
    mime = entity.get("mime")
    start_offset = entity.get("start_offset")
    end_offset = entity.get("end_offset")
    raw_score = raw.get("distance")
    score = float(raw_score) if raw_score is not None else fallback_score

    metadata = {
        "retrieval_source": source,
        "raw_distance": raw_score,
    }
    if stored_path and stored_path != path:
        metadata["stored_path"] = stored_path
    vector_id = entity.get("vector_id")
    if vector_id:
        metadata["vector_id"] = vector_id

    return SearchResultItem(
        id=str(raw.get("id")),
        path=path,
        score=score,
        chunk_id=chunk_id,
        snippet=snippet,
        mime=mime,
        source_type=entity.get("type") or source,
        start_offset=start_offset,
        end_offset=end_offset,
        metadata=metadata,
    )


async def _vector_search(query: str, top_k: int) -> List[SearchResultItem]:
    vector_db = VectorDBService()
    try:
        embedding = await get_text_embedding(query)
    except Exception:
        embedding = None
    if not embedding:
        return []

    try:
        raw_results = await vector_db.search_vectors(VECTOR_COLLECTION_NAME, embedding, max(top_k, 10))
    except Exception:
        return []

    results: List[SearchResultItem] = []
    for bucket in raw_results or []:
        for record in bucket or []:
            results.append(_normalize_result(record, "vector"))
    return results


async def _filename_search(query: str, page: int, page_size: int) -> Tuple[List[SearchResultItem], bool]:
    vector_db = VectorDBService()
    limit = max(page * page_size + 1, page_size * (page + 2))
    limit = min(limit, 2000)
    records: List[Dict[str, Any]] = []
    for collection_name in (FILE_COLLECTION_NAME, VECTOR_COLLECTION_NAME):
        try:
            raw_results = await vector_db.search_by_path(collection_name, query, limit)
        except Exception:
            continue
        if raw_results:
            records.extend(raw_results[0] or [])

    deduped: List[SearchResultItem] = []
    seen_paths: set[str] = set()
    for record in records or []:
        item = _normalize_result(record, "filename", fallback_score=1.0)
        stored_path = item.metadata.get("stored_path") if item.metadata else None
        key = item.path or stored_path or ""
        if key in seen_paths:
            continue
        seen_paths.add(key)
        deduped.append(item)

    start = max(page - 1, 0) * page_size
    end = start + page_size
    page_items = deduped[start:end]
    for offset, item in enumerate(page_items):
        if item.metadata is None:
            item.metadata = {}
        item.metadata.setdefault("retrieval_rank", start + offset)
    has_more = len(deduped) > end
    return page_items, has_more


class VirtualFSSearchService:
    @staticmethod
    async def search(query: str, top_k: int, mode: str, page: int, page_size: int):
        if mode == "vector":
            items = (await _vector_search(query, top_k))[:top_k]
            return {"items": items, "query": query, "mode": mode}
        if mode == "filename":
            items, has_more = await _filename_search(query, page, page_size)
            return {
                "items": items,
                "query": query,
                "mode": mode,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "has_more": has_more,
                },
            }
        items = (await _vector_search(query, top_k))[:top_k]
        return {"items": items, "query": query, "mode": mode}
