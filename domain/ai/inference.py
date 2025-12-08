from __future__ import annotations

import httpx
from typing import List, Sequence, Tuple

from models.database import AIModel, AIProvider
from domain.ai.service import AIProviderService


provider_service = AIProviderService


class MissingModelError(RuntimeError):
    pass


async def describe_image_base64(base64_image: str, detail: str = "high") -> str:
    """
    传入 base64 图片并返回描述文本。缺省时返回错误提示。
    """
    try:
        model, provider = await _require_model("vision")
        if provider.api_format == "openai":
            return await _describe_with_openai(provider, model, base64_image, detail)
        return await _describe_with_gemini(provider, model, base64_image, detail)
    except MissingModelError as exc:
        return str(exc)
    except httpx.ReadTimeout:
        return "请求超时，请稍后重试。"
    except Exception as exc:  # noqa: BLE001
        return f"请求失败: {exc}"


async def get_text_embedding(text: str) -> List[float]:
    """
    传入文本，返回嵌入向量。若未配置模型则抛出异常。
    """
    model, provider = await _require_model("embedding")
    if provider.api_format == "openai":
        return await _embedding_with_openai(provider, model, text)
    return await _embedding_with_gemini(provider, model, text)


async def rerank_texts(query: str, documents: Sequence[str]) -> List[float]:
    """调用重排序模型，为一组文档返回得分。未配置时返回空列表。"""
    if not documents:
        return []
    try:
        model, provider = await _require_model("rerank")
    except MissingModelError:
        return []

    try:
        if provider.api_format == "openai":
            return await _rerank_with_openai(provider, model, query, documents)
        return await _rerank_with_gemini(provider, model, query, documents)
    except Exception:  # noqa: BLE001
        return []


async def _require_model(ability: str) -> Tuple[AIModel, AIProvider]:
    model = await provider_service.get_default_model(ability)
    if not model:
        raise MissingModelError(f"未配置默认 {ability} 模型，请前往系统设置完成配置。")
    provider = getattr(model, "provider", None)
    if provider is None:
        await model.fetch_related("provider")
        provider = model.provider
    if provider is None:
        raise MissingModelError("模型缺少关联的提供商配置。")
    if not provider.base_url:
        raise MissingModelError("该提供商未设置 API 地址。")
    return model, provider


def _openai_endpoint(provider: AIProvider, path: str) -> str:
    base = (provider.base_url or "").rstrip("/")
    if not base:
        raise MissingModelError("提供商 API 地址未配置。")
    return f"{base}/{path.lstrip('/')}"


def _openai_headers(provider: AIProvider) -> dict:
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    return headers


def _gemini_endpoint(provider: AIProvider, path: str) -> str:
    base = (provider.base_url or "").rstrip("/")
    if not base:
        raise MissingModelError("提供商 API 地址未配置。")
    url = f"{base}/{path.lstrip('/')}"
    if provider.api_key:
        connector = "&" if "?" in url else "?"
        url = f"{url}{connector}key={provider.api_key}"
    return url


async def _describe_with_openai(provider: AIProvider, model: AIModel, base64_image: str, detail: str) -> str:
    url = _openai_endpoint(provider, "/chat/completions")
    payload = {
        "model": model.name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": detail,
                        },
                    },
                    {"type": "text", "text": "描述这个图片"},
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=_openai_headers(provider), json=payload)
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"]


async def _describe_with_gemini(provider: AIProvider, model: AIModel, base64_image: str, detail: str) -> str:
    detail_text = f"描述这个图片，细节等级：{detail}"
    model_name = model.name if model.name.startswith("models/") else f"models/{model.name}"
    url = _gemini_endpoint(provider, f"{model_name}:generateContent")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_image,
                        }
                    },
                    {"text": detail_text},
                ],
            }
        ]
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
        candidates = body.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
        return "\n".join(text_parts)


async def _embedding_with_openai(provider: AIProvider, model: AIModel, text: str) -> List[float]:
    url = _openai_endpoint(provider, "/embeddings")
    payload = {
        "model": model.name,
        "input": text,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=_openai_headers(provider), json=payload)
        response.raise_for_status()
        body = response.json()
        return body["data"][0]["embedding"]


async def _embedding_with_gemini(provider: AIProvider, model: AIModel, text: str) -> List[float]:
    model_name = model.name if model.name.startswith("models/") else f"models/{model.name}"
    url = _gemini_endpoint(provider, f"{model_name}:embedContent")
    payload = {
        "model": model_name,
        "content": {
            "parts": [{"text": text}],
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
        embedding = body.get("embedding") or {}
        return embedding.get("values") or []


async def _rerank_with_openai(
    provider: AIProvider,
    model: AIModel,
    query: str,
    documents: Sequence[str],
) -> List[float]:
    url = _openai_endpoint(provider, "/rerank")
    payload = {
        "model": model.name,
        "query": query,
        "documents": [
            {"id": str(idx), "text": content}
            for idx, content in enumerate(documents)
        ],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=_openai_headers(provider), json=payload)
        response.raise_for_status()
        body = response.json()
        results = body.get("results") or body.get("data") or []
        scores: List[float] = []
        for item in results:
            try:
                scores.append(float(item.get("score", 0.0)))
            except (TypeError, ValueError):
                scores.append(0.0)
        return scores


async def _rerank_with_gemini(
    provider: AIProvider,
    model: AIModel,
    query: str,
    documents: Sequence[str],
) -> List[float]:
    model_name = model.name if model.name.startswith("models/") else f"models/{model.name}"
    url = _gemini_endpoint(provider, f"{model_name}:rankContent")
    payload = {
        "query": {"text": query},
        "documents": [
            {"id": str(idx), "content": {"parts": [{"text": content}]}}
            for idx, content in enumerate(documents)
        ],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()

    scores: List[float] = []
    ranked = body.get("rankedDocuments") or body.get("results") or []
    for item in ranked:
        raw_score = item.get("relevanceScore") or item.get("score") or item.get("confidenceScore")
        try:
            scores.append(float(raw_score))
        except (TypeError, ValueError):
            scores.append(0.0)
    return scores
