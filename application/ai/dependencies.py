from __future__ import annotations

from application.ai.use_cases import AIProviderUseCases
from infrastructure.persistence.ai_repository import TortoiseAIRepository

ai_use_cases = AIProviderUseCases(TortoiseAIRepository())

__all__ = ["ai_use_cases"]
