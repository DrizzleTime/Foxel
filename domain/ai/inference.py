import json

import httpx
from typing import Any, AsyncIterator, Dict, List, Sequence, Tuple

from models.database import AIModel, AIProvider
from .service import AIProviderService


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


async def chat_completion(
    messages: List[Dict[str, Any]],
    *,
    ability: str = "chat",
    tools: List[Dict[str, Any]] | None = None,
    tool_choice: Any | None = None,
    temperature: float | None = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    model, provider = await _require_model(ability)
    if provider.api_format != "openai":
        raise MissingModelError("当前仅支持 OpenAI 兼容接口的对话模型。")
    return await _chat_with_openai(
        provider,
        model,
        messages,
        tools=tools,
        tool_choice=tool_choice,
        temperature=temperature,
        timeout=timeout,
    )


async def _chat_with_openai(
    provider: AIProvider,
    model: AIModel,
    messages: List[Dict[str, Any]],
    *,
    tools: List[Dict[str, Any]] | None,
    tool_choice: Any | None,
    temperature: float | None,
    timeout: float,
) -> Dict[str, Any]:
    url = _openai_endpoint(provider, "/chat/completions")
    payload: Dict[str, Any] = {
        "model": model.name,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
    if temperature is not None:
        payload["temperature"] = float(temperature)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=_openai_headers(provider), json=payload)
        response.raise_for_status()
        body = response.json()

    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("对话接口返回为空")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("对话接口返回格式异常")
    return message


async def chat_completion_stream(
    messages: List[Dict[str, Any]],
    *,
    ability: str = "chat",
    tools: List[Dict[str, Any]] | None = None,
    tool_choice: Any | None = None,
    temperature: float | None = None,
    timeout: float = 60.0,
) -> AsyncIterator[Dict[str, Any]]:
    model, provider = await _require_model(ability)
    if provider.api_format != "openai":
        raise MissingModelError("当前仅支持 OpenAI 兼容接口的对话模型。")
    async for event in _chat_stream_with_openai(
        provider,
        model,
        messages,
        tools=tools,
        tool_choice=tool_choice,
        temperature=temperature,
        timeout=timeout,
    ):
        yield event


async def _chat_stream_with_openai(
    provider: AIProvider,
    model: AIModel,
    messages: List[Dict[str, Any]],
    *,
    tools: List[Dict[str, Any]] | None,
    tool_choice: Any | None,
    temperature: float | None,
    timeout: float,
) -> AsyncIterator[Dict[str, Any]]:
    url = _openai_endpoint(provider, "/chat/completions")
    payload: Dict[str, Any] = {
        "model": model.name,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
    if temperature is not None:
        payload["temperature"] = float(temperature)

    content_parts: List[str] = []
    tool_call_map: Dict[int, Dict[str, Any]] = {}
    role = "assistant"
    finish_reason: str | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=_openai_headers(provider), json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0] if isinstance(choices[0], dict) else {}
                delta = choice.get("delta") if isinstance(choice, dict) else None
                delta = delta if isinstance(delta, dict) else {}

                if isinstance(delta.get("role"), str):
                    role = delta["role"]

                delta_content = delta.get("content")
                if isinstance(delta_content, str) and delta_content:
                    content_parts.append(delta_content)
                    yield {"type": "delta", "delta": delta_content}

                delta_tool_calls = delta.get("tool_calls")
                if isinstance(delta_tool_calls, list):
                    for item in delta_tool_calls:
                        if not isinstance(item, dict):
                            continue
                        idx = item.get("index")
                        if not isinstance(idx, int):
                            continue
                        entry = tool_call_map.setdefault(
                            idx,
                            {"id": None, "type": None, "function": {"name": None, "arguments": ""}},
                        )
                        if isinstance(item.get("id"), str) and item["id"].strip():
                            entry["id"] = item["id"]
                        if isinstance(item.get("type"), str) and item["type"].strip():
                            entry["type"] = item["type"]
                        fn = item.get("function")
                        if isinstance(fn, dict):
                            if isinstance(fn.get("name"), str) and fn["name"].strip():
                                entry["function"]["name"] = fn["name"]
                            args_part = fn.get("arguments")
                            if isinstance(args_part, str) and args_part:
                                entry["function"]["arguments"] += args_part

                fr = choice.get("finish_reason") if isinstance(choice, dict) else None
                if isinstance(fr, str) and fr:
                    finish_reason = fr

    content = "".join(content_parts)
    message: Dict[str, Any] = {"role": role, "content": content}
    if tool_call_map:
        tool_calls: List[Dict[str, Any]] = []
        for idx in sorted(tool_call_map.keys()):
            item = tool_call_map[idx]
            fn = item.get("function") if isinstance(item.get("function"), dict) else {}
            call_id = item.get("id") if isinstance(item.get("id"), str) and item.get("id") else f"call_{idx}"
            call_type = item.get("type") if isinstance(item.get("type"), str) and item.get("type") else "function"
            tool_calls.append({
                "id": call_id,
                "type": call_type,
                "function": {
                    "name": fn.get("name") or "",
                    "arguments": fn.get("arguments") or "",
                },
            })
        message["tool_calls"] = tool_calls

    yield {"type": "message", "message": message, "finish_reason": finish_reason}
