"""Service to read LLM config from shared database (managed by Laravel Filament)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LlmConfig

logger = logging.getLogger(__name__)


async def get_active_llm_config(db: AsyncSession) -> dict[str, Any] | None:
    """Ambil konfigurasi LLM yang aktif dari database (shared dgn Laravel).

    Returns dict dengan keys: provider, base_url, api_key, model
    atau None jika tidak ada config aktif.
    """
    try:
        result = await db.execute(
            select(LlmConfig).where(LlmConfig.is_active.is_(True)).limit(1)
        )
        config = result.scalar_one_or_none()
        if config is None:
            logger.info("No active LLM config found in database")
            return None

        return {
            "provider": config.provider,
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": config.model,
        }
    except Exception as e:
        logger.warning("Failed to read LLM config from database: %s", e)
        return None
