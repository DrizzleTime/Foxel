from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Tuple

import httpx
from tortoise.exceptions import DoesNotExist
from tortoise.transactions import in_transaction

from models.database import AIDefaultModel, AIModel, AIProvider


ABILITIES = ["chat", "vision", "embedding", "rerank", "voice", "tools"]

OPENAI_EMBEDDING_DIMS = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


def _normalize_embedding_dim(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        casted = int(value)
    except (TypeError, ValueError):
        return None
    return casted if casted > 0 else None


def _apply_embedding_dim_to_metadata(
    data: Dict[str, Any],
    embedding_dim: Optional[int],
    base_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source = base_metadata if isinstance(base_metadata, dict) else {}
    metadata: Dict[str, Any] = dict(source)
    override = data.get("metadata")
    if isinstance(override, dict) and override:
        metadata.update(override)
    if embedding_dim is None:
        metadata.pop("embedding_dimensions", None)
    else:
        metadata["embedding_dimensions"] = embedding_dim
    data["metadata"] = metadata or None
    return data


def normalize_capabilities(items: Optional[Iterable[str]]) -> List[str]:
    if not items:
        return []
    normalized = []
    for cap in items:
        key = str(cap).strip().lower()
        if key in ABILITIES and key not in normalized:
            normalized.append(key)
    return normalized


def infer_openai_capabilities(model_id: str) -> Tuple[List[str], Optional[int]]:
    lower = model_id.lower()
    caps = set()

    if any(keyword in lower for keyword in ["gpt", "chat", "turbo", "o1", "sonnet", "haiku", "thinking"]):
        caps.update({"chat", "tools"})

    if any(keyword in lower for keyword in ["vision", "gpt-4o", "gpt-4.1", "o1", "vision-preview", "omni"]):
        caps.add("vision")

    if any(keyword in lower for keyword in ["embed", "embedding"]):
        caps.add("embedding")

    if "rerank" in lower or "re-rank" in lower:
        caps.add("rerank")

    if any(keyword in lower for keyword in ["tts", "speech", "audio"]):
        caps.add("voice")

    embedding_dim = OPENAI_EMBEDDING_DIMS.get(model_id)
    return normalize_capabilities(caps), embedding_dim


def infer_gemini_capabilities(methods: Iterable[str]) -> List[str]:
    caps = set()
    for method in methods:
        m = method.lower()
        if m in {"generatecontent", "counttokens"}:
            caps.update({"chat", "tools", "vision"})
        if m == "embedcontent":
            caps.add("embedding")
        if m in {"generatespeech", "audiogeneration"}:
            caps.add("voice")
        if m == "rerank":
            caps.add("rerank")
    return normalize_capabilities(caps)


def serialize_provider(provider: AIProvider) -> Dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "identifier": provider.identifier,
        "provider_type": provider.provider_type,
        "api_format": provider.api_format,
        "base_url": provider.base_url,
        "api_key": provider.api_key,
        "logo_url": provider.logo_url,
        "extra_config": provider.extra_config or {},
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


def model_to_dict(model: AIModel, provider: Optional[AIProvider] = None) -> Dict[str, Any]:
    provider_obj = provider or getattr(model, "provider", None)
    provider_data = serialize_provider(provider_obj) if provider_obj else None
    return {
        "id": model.id,
        "provider_id": model.provider_id,
        "name": model.name,
        "display_name": model.display_name,
        "description": model.description,
        "capabilities": normalize_capabilities(model.capabilities),
        "context_window": model.context_window,
        "embedding_dimensions": model.embedding_dimensions,
        "metadata": model.metadata or {},
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "provider": provider_data,
    }


def provider_to_dict(provider: AIProvider, models: Optional[List[AIModel]] = None) -> Dict[str, Any]:
    data = serialize_provider(provider)
    if models is not None:
        data["models"] = [model_to_dict(m, provider=provider) for m in models]
    return data


class AIProviderService:
    async def list_providers(self) -> List[Dict[str, Any]]:
        providers = await AIProvider.all().order_by("id").prefetch_related("models")
        return [provider_to_dict(p, models=list(p.models)) for p in providers]

    async def get_provider(self, provider_id: int, with_models: bool = False) -> Dict[str, Any]:
        if with_models:
            provider = await AIProvider.get(id=provider_id)
            models = await provider.models.all()
            return provider_to_dict(provider, models=models)
        else:
            provider = await AIProvider.get(id=provider_id)
            return provider_to_dict(provider)

    async def create_provider(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = payload.copy()
        data.setdefault("extra_config", {})
        provider = await AIProvider.create(**data)
        return provider_to_dict(provider)

    async def update_provider(self, provider_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        provider = await AIProvider.get(id=provider_id)
        for field, value in payload.items():
            setattr(provider, field, value)
        await provider.save()
        return provider_to_dict(provider)

    async def delete_provider(self, provider_id: int) -> None:
        await AIProvider.filter(id=provider_id).delete()

    async def list_models(self, provider_id: int) -> List[Dict[str, Any]]:
        models = await AIModel.filter(provider_id=provider_id).order_by("id").prefetch_related("provider")
        return [model_to_dict(m) for m in models]

    async def create_model(self, provider_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = payload.copy()
        data["provider_id"] = provider_id
        data["capabilities"] = normalize_capabilities(data.get("capabilities"))
        embedding_dim = _normalize_embedding_dim(data.pop("embedding_dimensions", None))
        data = _apply_embedding_dim_to_metadata(data, embedding_dim)
        model = await AIModel.create(**data)
        await model.fetch_related("provider")
        return model_to_dict(model)

    async def update_model(self, model_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        model = await AIModel.get(id=model_id)
        data = payload.copy()
        if "capabilities" in data:
            data["capabilities"] = normalize_capabilities(data.get("capabilities"))
        embedding_dim = None
        if "embedding_dimensions" in data:
            embedding_dim = _normalize_embedding_dim(data.pop("embedding_dimensions", None))
            _apply_embedding_dim_to_metadata(data, embedding_dim, base_metadata=model.metadata)
        for field, value in data.items():
            setattr(model, field, value)
        if embedding_dim is not None or ("embedding_dimensions" in payload and embedding_dim is None):
            model.embedding_dimensions = embedding_dim
        await model.save()
        await model.fetch_related("provider")
        return model_to_dict(model)

    async def delete_model(self, model_id: int) -> None:
        await AIModel.filter(id=model_id).delete()

    async def fetch_remote_models(self, provider_id: int) -> List[Dict[str, Any]]:
        provider = await AIProvider.get(id=provider_id)
        return await self._get_remote_models(provider)

    async def _get_remote_models(self, provider: AIProvider) -> List[Dict[str, Any]]:
        if not provider.base_url:
            raise ValueError("Provider base_url is required for syncing models")

        fmt = (provider.api_format or "").lower()
        if fmt not in {"openai", "gemini"}:
            raise ValueError(f"Unsupported api_format '{provider.api_format}' for syncing models")

        if fmt == "openai":
            return await self._fetch_openai_models(provider)
        return await self._fetch_gemini_models(provider)

    async def sync_models(self, provider_id: int) -> Dict[str, int]:
        provider = await AIProvider.get(id=provider_id)
        remote_models = await self._get_remote_models(provider)

        created = 0
        updated = 0
        for entry in remote_models:
            defaults = entry.copy()
            model_id = defaults.pop("name")
            defaults["capabilities"] = normalize_capabilities(defaults.get("capabilities"))
            embedding_dim = _normalize_embedding_dim(defaults.pop("embedding_dimensions", None))
            defaults = _apply_embedding_dim_to_metadata(defaults, embedding_dim)
            obj, is_created = await AIModel.get_or_create(
                provider_id=provider.id,
                name=model_id,
                defaults=defaults,
            )
            if is_created:
                created += 1
                continue
            for field, value in defaults.items():
                setattr(obj, field, value)
            if embedding_dim is not None or ("embedding_dimensions" in entry and embedding_dim is None):
                obj.embedding_dimensions = embedding_dim
            await obj.save()
            updated += 1

        return {"created": created, "updated": updated}

    async def get_default_models(self) -> Dict[str, Optional[Dict[str, Any]]]:
        defaults = await AIDefaultModel.all().prefetch_related("model__provider")
        result: Dict[str, Optional[Dict[str, Any]]] = {ability: None for ability in ABILITIES}
        for item in defaults:
            result[item.ability] = model_to_dict(item.model, provider=item.model.provider)  # type: ignore[attr-defined]
        return result

    async def set_default_models(self, mapping: Dict[str, Optional[int]]) -> Dict[str, Optional[Dict[str, Any]]]:
        normalized = {ability: mapping.get(ability) for ability in ABILITIES}
        async with in_transaction() as connection:
            for ability, model_id in normalized.items():
                record = await AIDefaultModel.get_or_none(ability=ability)
                if model_id:
                    try:
                        model = await AIModel.get(id=model_id)
                    except DoesNotExist:
                        raise ValueError(f"Model {model_id} not found")
                    if record:
                        record.model_id = model_id
                        await record.save(using_db=connection)
                    else:
                        await AIDefaultModel.create(ability=ability, model_id=model_id)
                elif record:
                    await record.delete(using_db=connection)
        return await self.get_default_models()

    async def get_default_model(self, ability: str) -> Optional[AIModel]:
        ability_key = ability.lower()
        if ability_key not in ABILITIES:
            return None
        record = await AIDefaultModel.get_or_none(ability=ability_key)
        if not record:
            return None
        model = await AIModel.get_or_none(id=record.model_id)
        if model:
            await model.fetch_related("provider")
        return model

    async def _fetch_openai_models(self, provider: AIProvider) -> List[Dict[str, Any]]:
        base_url = provider.base_url.rstrip("/")
        url = f"{base_url}/models"
        headers = {}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()

        data = payload.get("data", [])
        entries: List[Dict[str, Any]] = []
        for item in data:
            model_id = item.get("id")
            if not model_id:
                continue
            capabilities, embedding_dim = infer_openai_capabilities(model_id)
            entries.append({
                "name": model_id,
                "display_name": item.get("display_name"),
                "description": item.get("description"),
                "capabilities": capabilities,
                "context_window": item.get("context_window"),
                "embedding_dimensions": embedding_dim,
                "metadata": item,
            })
        return entries

    async def _fetch_gemini_models(self, provider: AIProvider) -> List[Dict[str, Any]]:
        base_url = provider.base_url.rstrip("/")
        suffix = "/models"
        if provider.api_key:
            suffix += f"?key={provider.api_key}"
        url = f"{base_url}{suffix}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        data = payload.get("models", [])
        entries: List[Dict[str, Any]] = []
        for item in data:
            model_id = item.get("name")
            if not model_id:
                continue
            methods = item.get("supportedGenerationMethods") or []
            capabilities = infer_gemini_capabilities(methods)
            entries.append({
                "name": model_id,
                "display_name": item.get("displayName"),
                "description": item.get("description"),
                "capabilities": capabilities,
                "context_window": item.get("inputTokenLimit"),
                "embedding_dimensions": item.get("embeddingDimensions"),
                "metadata": item,
            })
        return entries
