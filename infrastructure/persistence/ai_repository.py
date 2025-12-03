from __future__ import annotations

from typing import Dict, List, Optional

from tortoise.exceptions import DoesNotExist

from domain.ai.entities import AIDefaultModelEntity, AIModelEntity, AIProviderEntity
from domain.ai.repositories import AIRepository
from models.database import AIDefaultModel, AIModel, AIProvider


def _provider_to_entity(model: AIProvider) -> AIProviderEntity:
    return AIProviderEntity(
        id=model.id,
        name=model.name,
        identifier=model.identifier,
        provider_type=model.provider_type,
        api_format=model.api_format,
        base_url=model.base_url,
        api_key=model.api_key,
        logo_url=model.logo_url,
        extra_config=model.extra_config or {},
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _model_to_entity(model: AIModel, provider: AIProvider | None = None) -> AIModelEntity:
    provider_entity = _provider_to_entity(provider) if provider else None
    return AIModelEntity(
        id=model.id,
        provider_id=model.provider_id,
        name=model.name,
        display_name=model.display_name,
        description=model.description,
        capabilities=model.capabilities or [],
        context_window=model.context_window,
        embedding_dimensions=model.embedding_dimensions,
        metadata=model.metadata or {},
        created_at=model.created_at,
        updated_at=model.updated_at,
        provider=provider_entity,
    )


class TortoiseAIRepository(AIRepository):
    async def list_providers(self) -> List[AIProviderEntity]:
        providers = await AIProvider.all().order_by("id").prefetch_related("models")
        result: List[AIProviderEntity] = []
        for provider in providers:
            result.append(_provider_to_entity(provider))
        return result

    async def get_provider(self, provider_id: int) -> AIProviderEntity | None:
        provider = await AIProvider.get_or_none(id=provider_id)
        return _provider_to_entity(provider) if provider else None

    async def create_provider(self, data: Dict) -> AIProviderEntity:
        provider = await AIProvider.create(**data)
        return _provider_to_entity(provider)

    async def update_provider(self, provider_id: int, data: Dict) -> AIProviderEntity:
        provider = await AIProvider.get(id=provider_id)
        for field, value in data.items():
            setattr(provider, field, value)
        await provider.save()
        return _provider_to_entity(provider)

    async def delete_provider(self, provider_id: int) -> None:
        await AIProvider.filter(id=provider_id).delete()

    async def list_models(self, provider_id: int) -> List[AIModelEntity]:
        models = (
            await AIModel.filter(provider_id=provider_id)
            .order_by("id")
            .prefetch_related("provider")
        )
        return [_model_to_entity(m, provider=m.provider) for m in models]

    async def get_model(self, model_id: int) -> AIModelEntity | None:
        model = await AIModel.get_or_none(id=model_id)
        if not model:
            return None
        await model.fetch_related("provider")
        return _model_to_entity(model, provider=model.provider)

    async def create_model(self, provider_id: int, data: Dict) -> AIModelEntity:
        model = await AIModel.create(provider_id=provider_id, **data)
        await model.fetch_related("provider")
        return _model_to_entity(model, provider=model.provider)

    async def update_model(self, model_id: int, data: Dict) -> AIModelEntity:
        model = await AIModel.get(id=model_id)
        for field, value in data.items():
            setattr(model, field, value)
        await model.save()
        await model.fetch_related("provider")
        return _model_to_entity(model, provider=model.provider)

    async def delete_model(self, model_id: int) -> None:
        await AIModel.filter(id=model_id).delete()

    async def list_default_models(self) -> List[AIDefaultModelEntity]:
        records = await AIDefaultModel.all().prefetch_related("model__provider")
        result: List[AIDefaultModelEntity] = []
        for item in records:
            model_entity = None
            if item.model:
                model_entity = _model_to_entity(item.model, provider=item.model.provider)  # type: ignore[attr-defined]
            result.append(AIDefaultModelEntity(ability=item.ability, model=model_entity))
        return result

    async def set_default_model(self, ability: str, model_id: Optional[int]) -> None:
        record = await AIDefaultModel.get_or_none(ability=ability)
        if model_id:
            try:
                model = await AIModel.get(id=model_id)
            except DoesNotExist as exc:
                raise ValueError(f"Model {model_id} not found") from exc
            if record:
                record.model_id = model.id
                await record.save()
            else:
                await AIDefaultModel.create(ability=ability, model_id=model.id)
        elif record:
            await record.delete()

    async def get_default_model(self, ability: str) -> AIModelEntity | None:
        record = await AIDefaultModel.get_or_none(ability=ability)
        if not record:
            return None
        model = await AIModel.get_or_none(id=record.model_id).prefetch_related("provider")  # type: ignore[attr-defined]
        if not model:
            return None
        return _model_to_entity(model, provider=model.provider)

    async def get_model_by_name(self, provider_id: int, name: str) -> AIModelEntity | None:
        model = await AIModel.get_or_none(provider_id=provider_id, name=name)
        if not model:
            return None
        await model.fetch_related("provider")
        return _model_to_entity(model, provider=model.provider)


__all__ = ["TortoiseAIRepository"]
