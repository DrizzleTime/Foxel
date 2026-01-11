import json

import httpx
from typing import Any, AsyncIterator, Dict, List, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
        fmt = str(provider.api_format or "").lower()
        if fmt == "openai":
            return await _describe_with_openai(provider, model, base64_image, detail)
        if fmt == "gemini":
            return await _describe_with_gemini(provider, model, base64_image, detail)
        if fmt == "anthropic":
            return await _describe_with_anthropic(provider, model, base64_image, detail)
        if fmt == "ollama":
            return await _describe_with_ollama(provider, model, base64_image)
        raise MissingModelError(f"不支持的视觉模型接口类型: {provider.api_format}")
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
    fmt = str(provider.api_format or "").lower()
    if fmt == "openai":
        return await _embedding_with_openai(provider, model, text)
    if fmt == "gemini":
        return await _embedding_with_gemini(provider, model, text)
    if fmt == "ollama":
        return await _embedding_with_ollama(provider, model, text)
    raise MissingModelError(f"不支持的嵌入模型接口类型: {provider.api_format}")


async def rerank_texts(query: str, documents: Sequence[str]) -> List[float]:
    """调用重排序模型，为一组文档返回得分。未配置时返回空列表。"""
    if not documents:
        return []
    try:
        model, provider = await _require_model("rerank")
    except MissingModelError:
        return []

    try:
        fmt = str(provider.api_format or "").lower()
        if fmt == "openai":
            return await _rerank_with_openai(provider, model, query, documents)
        if fmt == "gemini":
            return await _rerank_with_gemini(provider, model, query, documents)
        return []
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
    raw_base = str(provider.base_url or "").strip()
    if not raw_base:
        raise MissingModelError("提供商 API 地址未配置。")

    base = urlsplit(raw_base)
    extra_path, _, extra_query = str(path or "").partition("?")

    base_path = base.path.rstrip("/")
    extra_path = "/" + extra_path.lstrip("/")
    merged_path = (base_path + extra_path) if base_path else extra_path

    query_pairs = list(parse_qsl(base.query, keep_blank_values=True))
    if extra_query:
        query_pairs.extend(parse_qsl(extra_query, keep_blank_values=True))

    query_map = {k: v for k, v in query_pairs if k}
    if _is_azure_openai(provider) and "api-version" not in query_map:
        query_map["api-version"] = "2024-02-15-preview"

    merged_query = urlencode(query_map, doseq=True)
    return urlunsplit((base.scheme, base.netloc, merged_path, merged_query, base.fragment))


def _openai_headers(provider: AIProvider) -> dict:
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        if _is_azure_openai(provider):
            headers["api-key"] = provider.api_key
        else:
            headers["Authorization"] = f"Bearer {provider.api_key}"
    return headers


def _is_azure_openai(provider: AIProvider) -> bool:
    identifier = str(provider.identifier or "").lower()
    if identifier == "azure-openai":
        return True
    base_url = str(provider.base_url or "").lower()
    return ".openai.azure.com" in base_url


def _gemini_endpoint(provider: AIProvider, path: str) -> str:
    base = (provider.base_url or "").rstrip("/")
    if not base:
        raise MissingModelError("提供商 API 地址未配置。")
    url = f"{base}/{path.lstrip('/')}"
    if provider.api_key:
        connector = "&" if "?" in url else "?"
        url = f"{url}{connector}key={provider.api_key}"
    return url


ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_DEFAULT_MAX_TOKENS = 1024


def _anthropic_endpoint(provider: AIProvider, path: str) -> str:
    raw_base = str(provider.base_url or "").strip()
    if not raw_base:
        raise MissingModelError("提供商 API 地址未配置。")

    base = urlsplit(raw_base)
    extra_path, _, extra_query = str(path or "").partition("?")

    base_path = base.path.rstrip("/")
    extra_path = "/" + extra_path.lstrip("/")
    merged_path = (base_path + extra_path) if base_path else extra_path

    query_pairs = list(parse_qsl(base.query, keep_blank_values=True))
    if extra_query:
        query_pairs.extend(parse_qsl(extra_query, keep_blank_values=True))
    merged_query = urlencode(query_pairs, doseq=True)
    return urlunsplit((base.scheme, base.netloc, merged_path, merged_query, base.fragment))


def _anthropic_headers(provider: AIProvider) -> dict:
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    if provider.api_key:
        headers["x-api-key"] = provider.api_key
    extra = provider.extra_config if isinstance(provider.extra_config, dict) else {}
    version = extra.get("anthropic_version") or extra.get("anthropic-version")
    if isinstance(version, str) and version.strip():
        headers["anthropic-version"] = version.strip()
    beta = extra.get("anthropic_beta") or extra.get("anthropic-beta")
    if isinstance(beta, str) and beta.strip():
        headers["anthropic-beta"] = beta.strip()
    return headers


def _openai_content_to_anthropic_blocks(content: Any) -> List[Dict[str, Any]]:
    if content is None:
        return []

    if isinstance(content, str):
        text = content.strip("\n")
        return [{"type": "text", "text": text}] if text else []

    if isinstance(content, list):
        blocks: List[Dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = part.get("type")
            if part_type == "text" and isinstance(part.get("text"), str):
                text = part["text"].strip("\n")
                if text:
                    blocks.append({"type": "text", "text": text})
                continue
            if part_type == "image_url" and isinstance(part.get("image_url"), dict):
                url = part["image_url"].get("url")
                if not isinstance(url, str) or not url.startswith("data:") or ";base64," not in url:
                    continue
                header, data = url.split(",", 1)
                media_type = header[5:].split(";", 1)[0] or "image/jpeg"
                data = data.strip()
                if not data:
                    continue
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
        return blocks

    return [{"type": "text", "text": str(content)}]


def _openai_tools_to_anthropic(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") != "function":
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        description = fn.get("description")
        input_schema = fn.get("parameters")
        input_schema = input_schema if isinstance(input_schema, dict) else {}
        out.append({
            "name": name,
            "description": description if isinstance(description, str) else "",
            "input_schema": input_schema,
        })
    return out


def _openai_messages_to_anthropic(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    system_parts: List[str] = []
    prepared: List[Dict[str, Any]] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "system":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                system_parts.append(content.strip())
            continue

        if role == "tool":
            tool_use_id = msg.get("tool_call_id")
            content = msg.get("content")
            tool_use_id = str(tool_use_id or "").strip()
            content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            if not tool_use_id:
                prepared.append({"role": "user", "content": [{"type": "text", "text": content_str}]})
            else:
                prepared.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content_str}],
                })
            continue

        if role not in {"user", "assistant"}:
            continue

        blocks = _openai_content_to_anthropic_blocks(msg.get("content"))
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                call_id = call.get("id")
                fn = call.get("function")
                fn = fn if isinstance(fn, dict) else {}
                name = fn.get("name")
                args = fn.get("arguments")
                if not isinstance(name, str) or not name.strip():
                    continue
                args_obj: Dict[str, Any] = {}
                if isinstance(args, str) and args.strip():
                    try:
                        parsed = json.loads(args)
                        if isinstance(parsed, dict):
                            args_obj = parsed
                    except json.JSONDecodeError:
                        args_obj = {}
                blocks.append({
                    "type": "tool_use",
                    "id": str(call_id or ""),
                    "name": name,
                    "input": args_obj,
                })

        if not blocks:
            blocks = [{"type": "text", "text": ""}]
        prepared.append({"role": role, "content": blocks})

    merged: List[Dict[str, Any]] = []
    for item in prepared:
        if merged and merged[-1].get("role") == item.get("role"):
            merged[-1]["content"].extend(item.get("content") or [])
            continue
        merged.append(item)

    if merged and merged[0].get("role") != "user":
        merged.insert(0, {"role": "user", "content": [{"type": "text", "text": ""}]})

    system = "\n\n".join(system_parts).strip()
    return system, merged


def _anthropic_body_to_openai_message(body: Dict[str, Any]) -> Dict[str, Any]:
    content_blocks = body.get("content") or []
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []

    if isinstance(content_blocks, list):
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                text_parts.append(block["text"])
                continue
            if block_type == "tool_use":
                call_id = block.get("id")
                name = block.get("name")
                tool_input = block.get("input")
                tool_input = tool_input if isinstance(tool_input, dict) else {}
                if not isinstance(name, str) or not name.strip():
                    continue
                tool_calls.append({
                    "id": str(call_id or ""),
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(tool_input, ensure_ascii=False),
                    },
                })

    message: Dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


async def _chat_with_anthropic(
    provider: AIProvider,
    model: AIModel,
    messages: List[Dict[str, Any]],
    *,
    tools: List[Dict[str, Any]] | None,
    temperature: float | None,
    timeout: float,
) -> Dict[str, Any]:
    url = _anthropic_endpoint(provider, "/messages")
    system, anthropic_messages = _openai_messages_to_anthropic(messages)

    payload: Dict[str, Any] = {
        "model": model.name,
        "max_tokens": ANTHROPIC_DEFAULT_MAX_TOKENS,
        "messages": anthropic_messages,
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = _openai_tools_to_anthropic(tools)
    if temperature is not None:
        payload["temperature"] = float(temperature)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=_anthropic_headers(provider), json=payload)
        response.raise_for_status()
        body = response.json()

    return _anthropic_body_to_openai_message(body if isinstance(body, dict) else {})


async def _chat_stream_with_anthropic(
    provider: AIProvider,
    model: AIModel,
    messages: List[Dict[str, Any]],
    *,
    tools: List[Dict[str, Any]] | None,
    temperature: float | None,
    timeout: float,
) -> AsyncIterator[Dict[str, Any]]:
    url = _anthropic_endpoint(provider, "/messages")
    system, anthropic_messages = _openai_messages_to_anthropic(messages)

    payload: Dict[str, Any] = {
        "model": model.name,
        "max_tokens": ANTHROPIC_DEFAULT_MAX_TOKENS,
        "messages": anthropic_messages,
        "stream": True,
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = _openai_tools_to_anthropic(tools)
    if temperature is not None:
        payload["temperature"] = float(temperature)

    content_parts: List[str] = []
    tool_call_map: Dict[int, Dict[str, Any]] = {}
    finish_reason: str | None = None
    current_event: str | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=_anthropic_headers(provider), json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue

                if current_event == "content_block_start":
                    idx = chunk.get("index")
                    block = chunk.get("content_block")
                    if not isinstance(idx, int) or not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    tool_call_map[idx] = {
                        "id": str(block.get("id") or ""),
                        "name": str(block.get("name") or ""),
                        "input": block.get("input") if isinstance(block.get("input"), dict) else None,
                        "arguments": "",
                    }
                    continue

                if current_event == "content_block_delta":
                    idx = chunk.get("index")
                    delta = chunk.get("delta")
                    if not isinstance(idx, int) or not isinstance(delta, dict):
                        continue
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            content_parts.append(text)
                            yield {"type": "delta", "delta": text}
                        continue
                    if delta_type == "input_json_delta":
                        partial = delta.get("partial_json")
                        if not isinstance(partial, str) or not partial:
                            continue
                        entry = tool_call_map.setdefault(
                            idx,
                            {"id": "", "name": "", "input": None, "arguments": ""},
                        )
                        entry["arguments"] += partial
                        continue

                if current_event == "message_delta":
                    delta = chunk.get("delta")
                    if isinstance(delta, dict) and isinstance(delta.get("stop_reason"), str):
                        finish_reason = delta["stop_reason"]
                    continue

                if current_event == "message_stop":
                    break

    content = "".join(content_parts)
    message: Dict[str, Any] = {"role": "assistant", "content": content}

    tool_calls: List[Dict[str, Any]] = []
    for idx in sorted(tool_call_map.keys()):
        item = tool_call_map[idx]
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        args_text = str(item.get("arguments") or "")
        if not args_text:
            args_obj = item.get("input")
            args_obj = args_obj if isinstance(args_obj, dict) else {}
            args_text = json.dumps(args_obj, ensure_ascii=False)
        tool_calls.append({
            "id": str(item.get("id") or f"call_{idx}"),
            "type": "function",
            "function": {"name": name, "arguments": args_text},
        })

    if tool_calls:
        message["tool_calls"] = tool_calls

    yield {"type": "message", "message": message, "finish_reason": finish_reason}


def _ollama_endpoint(provider: AIProvider, path: str) -> str:
    raw_base = str(provider.base_url or "").strip()
    if not raw_base:
        raise MissingModelError("提供商 API 地址未配置。")

    base = urlsplit(raw_base)
    extra_path, _, extra_query = str(path or "").partition("?")

    base_path = base.path.rstrip("/")
    extra_path = "/" + extra_path.lstrip("/")
    merged_path = (base_path + extra_path) if base_path else extra_path

    query_pairs = list(parse_qsl(base.query, keep_blank_values=True))
    if extra_query:
        query_pairs.extend(parse_qsl(extra_query, keep_blank_values=True))
    merged_query = urlencode(query_pairs, doseq=True)
    return urlunsplit((base.scheme, base.netloc, merged_path, merged_query, base.fragment))


def _openai_content_to_ollama_message(content: Any) -> Tuple[str, List[str]]:
    if content is None:
        return "", []
    if isinstance(content, str):
        return content, []

    if isinstance(content, list):
        text_parts: List[str] = []
        images: List[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
                continue
            if part.get("type") == "image_url" and isinstance(part.get("image_url"), dict):
                url = part["image_url"].get("url")
                if not isinstance(url, str) or not url.startswith("data:") or ";base64," not in url:
                    continue
                _, data = url.split(",", 1)
                data = data.strip()
                if data:
                    images.append(data)
        return "\n".join([t for t in text_parts if t]), images

    return str(content), []


def _openai_messages_to_ollama(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "tool":
            content = msg.get("content")
            call_id = str(msg.get("tool_call_id") or "").strip()
            content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            if call_id:
                content_str = f"[tool:{call_id}] {content_str}"
            out.append({"role": "user", "content": content_str})
            continue

        if role not in {"system", "user", "assistant"}:
            continue

        text, images = _openai_content_to_ollama_message(msg.get("content"))
        item: Dict[str, Any] = {"role": role, "content": text}
        if images:
            item["images"] = images
        out.append(item)
    return out


def _ollama_message_to_openai(message: Dict[str, Any]) -> Dict[str, Any]:
    role = message.get("role") if isinstance(message.get("role"), str) else "assistant"
    content = message.get("content") if isinstance(message.get("content"), str) else ""

    tool_calls: List[Dict[str, Any]] = []
    raw_tool_calls = message.get("tool_calls")
    if isinstance(raw_tool_calls, list):
        for idx, call in enumerate(raw_tool_calls):
            if not isinstance(call, dict):
                continue
            fn = call.get("function")
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            raw_args = fn.get("arguments")
            if isinstance(raw_args, dict):
                args_text = json.dumps(raw_args, ensure_ascii=False)
            elif isinstance(raw_args, str):
                args_text = raw_args
            else:
                args_text = ""
            tool_calls.append({
                "id": str(call.get("id") or f"call_{idx}"),
                "type": "function",
                "function": {"name": name, "arguments": args_text},
            })

    out: Dict[str, Any] = {"role": role, "content": content}
    if tool_calls:
        out["tool_calls"] = tool_calls
    return out


async def _chat_with_ollama(
    provider: AIProvider,
    model: AIModel,
    messages: List[Dict[str, Any]],
    *,
    tools: List[Dict[str, Any]] | None,
    temperature: float | None,
    timeout: float,
) -> Dict[str, Any]:
    url = _ollama_endpoint(provider, "/api/chat")
    ollama_messages = _openai_messages_to_ollama(messages)

    payload: Dict[str, Any] = {
        "model": model.name,
        "messages": ollama_messages,
        "stream": False,
    }
    if temperature is not None:
        payload["options"] = {"temperature": float(temperature)}

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()

    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("对话接口返回格式异常")
    return _ollama_message_to_openai(message)


async def _chat_stream_with_ollama(
    provider: AIProvider,
    model: AIModel,
    messages: List[Dict[str, Any]],
    *,
    tools: List[Dict[str, Any]] | None,
    temperature: float | None,
    timeout: float,
) -> AsyncIterator[Dict[str, Any]]:
    url = _ollama_endpoint(provider, "/api/chat")
    ollama_messages = _openai_messages_to_ollama(messages)

    payload: Dict[str, Any] = {
        "model": model.name,
        "messages": ollama_messages,
        "stream": True,
    }
    if temperature is not None:
        payload["options"] = {"temperature": float(temperature)}

    content_parts: List[str] = []
    last_message: Dict[str, Any] | None = None
    finish_reason: str | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue

                msg = chunk.get("message")
                if isinstance(msg, dict):
                    last_message = msg
                    delta = msg.get("content")
                    if isinstance(delta, str) and delta:
                        content_parts.append(delta)
                        yield {"type": "delta", "delta": delta}

                done = chunk.get("done")
                if done is True:
                    finish_reason = str(chunk.get("done_reason") or "stop")
                    break

    if not isinstance(last_message, dict):
        last_message = {"role": "assistant", "content": "".join(content_parts)}
    else:
        last_message = dict(last_message)
        if content_parts:
            last_message["content"] = "".join(content_parts)

    message = _ollama_message_to_openai(last_message)
    yield {"type": "message", "message": message, "finish_reason": finish_reason}


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


async def _describe_with_anthropic(provider: AIProvider, model: AIModel, base64_image: str, detail: str) -> str:
    url = _anthropic_endpoint(provider, "/messages")
    detail_text = f"描述这个图片，细节等级：{detail}"
    payload: Dict[str, Any] = {
        "model": model.name,
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_image,
                        },
                    },
                    {"type": "text", "text": detail_text},
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=_anthropic_headers(provider), json=payload)
        response.raise_for_status()
        body = response.json()
    message = _anthropic_body_to_openai_message(body if isinstance(body, dict) else {})
    return str(message.get("content") or "")


async def _describe_with_ollama(provider: AIProvider, model: AIModel, base64_image: str) -> str:
    url = _ollama_endpoint(provider, "/api/chat")
    payload = {
        "model": model.name,
        "messages": [
            {"role": "user", "content": "描述这个图片", "images": [base64_image]},
        ],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()

    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")


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


async def _embedding_with_ollama(provider: AIProvider, model: AIModel, text: str) -> List[float]:
    url = _ollama_endpoint(provider, "/api/embeddings")
    payload = {
        "model": model.name,
        "prompt": text,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()

    embedding = body.get("embedding") if isinstance(body, dict) else None
    if not isinstance(embedding, list):
        return []
    return [float(v) for v in embedding if isinstance(v, (int, float))]


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
    fmt = str(provider.api_format or "").lower()
    if fmt == "openai":
        return await _chat_with_openai(
            provider,
            model,
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            timeout=timeout,
        )
    if fmt == "anthropic":
        return await _chat_with_anthropic(
            provider,
            model,
            messages,
            tools=tools,
            temperature=temperature,
            timeout=timeout,
        )
    if fmt == "ollama":
        return await _chat_with_ollama(
            provider,
            model,
            messages,
            tools=tools,
            temperature=temperature,
            timeout=timeout,
        )
    raise MissingModelError(f"当前不支持该对话模型接口类型: {provider.api_format}")


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
    fmt = str(provider.api_format or "").lower()
    if fmt == "openai":
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
        return
    if fmt == "anthropic":
        async for event in _chat_stream_with_anthropic(
            provider,
            model,
            messages,
            tools=tools,
            temperature=temperature,
            timeout=timeout,
        ):
            yield event
        return
    if fmt == "ollama":
        async for event in _chat_stream_with_ollama(
            provider,
            model,
            messages,
            tools=tools,
            temperature=temperature,
            timeout=timeout,
        ):
            yield event
        return
    raise MissingModelError(f"当前不支持该对话模型接口类型: {provider.api_format}")


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
