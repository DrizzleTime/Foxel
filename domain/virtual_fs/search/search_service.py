import asyncio
import logging
from collections.abc import Awaitable
from typing import Any, Dict, List

from domain.ai import VECTOR_COLLECTION_NAME, VectorDBService, get_text_embedding
from ..types import SearchResultItem
from .lexical import LexicalHit, get_lexical_index

RRF_K = 60
logger = logging.getLogger(__name__)


def _candidate_limit(top_k: int) -> int:
    return min(max(top_k * 5, 50), 100)


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
    heading = entity.get("heading")
    if heading:
        metadata["heading"] = heading
    for key in ("page", "sheet", "slide"):
        value = entity.get(key)
        if value is not None and value != "":
            metadata[key] = value

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


def _from_lexical(hit: LexicalHit) -> SearchResultItem:
    metadata: Dict[str, Any] = {
        "retrieval_source": "bm25",
        "bm25_score": hit.score,
    }
    if hit.heading:
        metadata["heading"] = hit.heading
    if hit.page is not None:
        metadata["page"] = hit.page
    if hit.sheet:
        metadata["sheet"] = hit.sheet
    if hit.slide is not None:
        metadata["slide"] = hit.slide
    return SearchResultItem(
        id=f"bm25:{hit.source_path}:{hit.chunk_id}",
        path=hit.source_path,
        score=0.0,
        chunk_id=hit.chunk_id or None,
        snippet=hit.snippet or None,
        mime=hit.mime or None,
        source_type=hit.kind or "bm25",
        metadata=metadata,
    )


def _channel(item: SearchResultItem) -> str:
    source = (item.metadata or {}).get("retrieval_source")
    if source in {"bm25", "vector"}:
        return str(source)
    return "vector"


def reciprocal_rank_fusion(ranked_lists: List[List[SearchResultItem]], k: int = RRF_K) -> List[SearchResultItem]:
    """RRF。rank 从 1 开始，score += 1/(k+rank)。同一路径只留名次更好的那条摘要。"""
    fused: Dict[str, Dict[str, Any]] = {}
    for items in ranked_lists:
        for rank, item in enumerate(items, start=1):
            path = item.path
            if not path:
                continue
            channel = _channel(item)
            bonus = 1.0 / (k + rank)
            slot = fused.get(path)
            if slot is None:
                fused[path] = {"item": item, "score": bonus, "best_rank": rank, "channels": [channel]}
                continue
            slot["score"] += bonus
            if channel not in slot["channels"]:
                slot["channels"].append(channel)
            if rank < slot["best_rank"]:
                slot["item"] = item
                slot["best_rank"] = rank

    results: List[SearchResultItem] = []
    for slot in fused.values():
        item = slot["item"].model_copy(deep=True)
        channels = list(slot["channels"])
        metadata = dict(item.metadata or {})
        metadata["channels"] = channels
        metadata["rrf_score"] = slot["score"]
        metadata["retrieval_source"] = "hybrid" if len(channels) > 1 else channels[0]
        item.metadata = metadata
        item.score = slot["score"]
        results.append(item)
    results.sort(key=lambda item: item.score, reverse=True)
    return results


async def _vector_search(query: str, top_k: int) -> List[SearchResultItem]:
    vector_db = VectorDBService()
    embedding = await get_text_embedding(query)
    if not embedding:
        raise ValueError("Embedding model returned an empty vector")

    raw_results = await vector_db.search_vectors(VECTOR_COLLECTION_NAME, embedding, max(top_k, 10))

    results_by_path: Dict[str, SearchResultItem] = {}
    for bucket in raw_results or []:
        for record in bucket or []:
            item = _normalize_result(record, "vector")
            existing = results_by_path.get(item.path)
            if existing is None or item.score > existing.score:
                results_by_path[item.path] = item
    return sorted(results_by_path.values(), key=lambda item: item.score, reverse=True)


async def _bm25_search(query: str, limit: int) -> List[SearchResultItem]:
    hits = await get_lexical_index().search(query, limit)
    return [_from_lexical(hit) for hit in hits]


async def _hybrid_search(query: str, top_k: int) -> tuple[List[SearchResultItem], List[Dict[str, str]]]:
    top_k = max(int(top_k), 1)
    limit = _candidate_limit(top_k)
    warnings: List[Dict[str, str]] = []

    async def run_channel(source: str, search: Awaitable[List[SearchResultItem]]) -> List[SearchResultItem]:
        try:
            return await search
        except Exception as exc:
            logger.exception("Search channel failed (source=%s)", source)
            warnings.append({"source": source, "message": str(exc) or type(exc).__name__})
            return []

    vector_items, bm25_items = await asyncio.gather(
        run_channel("vector", _vector_search(query, limit)),
        run_channel("bm25", _bm25_search(query, limit)),
    )
    return reciprocal_rank_fusion([vector_items, bm25_items])[:top_k], warnings


class VirtualFSSearchService:
    @staticmethod
    async def search(query: str, top_k: int, mode: str = "hybrid", page: int = 1, page_size: int = 10):
        """mode、page、page_size 保留给旧客户端，搜索始终是 BM25 与向量的 RRF 融合。"""
        del mode, page, page_size
        items, warnings = await _hybrid_search(query, top_k)
        return {"items": items, "query": query, "mode": "hybrid", "warnings": warnings}
