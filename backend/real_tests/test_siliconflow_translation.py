from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx
import pytest

from sakuraplayer.catalog.translation.adapter import (
    OpenAiTranslationAdapter,
    TranslationRequest,
)
from sakuraplayer.catalog.translation.config import AiConfigurationSnapshot


def test_siliconflow_qwen35_translates_one_synthetic_text() -> None:
    if os.environ.get("SAKURAPLAYER_RUN_REALAI") != "1":
        pytest.skip("real AI gate requires explicit opt-in")
    base_url = os.environ["SAKURAPLAYER_REAL_AI_BASE_URL"]
    api_key = os.environ["SAKURAPLAYER_REAL_AI_API_KEY"]
    model = os.environ["SAKURAPLAYER_REAL_AI_MODEL"]
    assert urlsplit(base_url).hostname == "api.siliconflow.cn"
    assert model.casefold().startswith("qwen/qwen3.5-")
    configuration = AiConfigurationSnapshot(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=60,
        version=1,
    )
    request = TranslationRequest(
        kind="movie_description",
        source_text="A quiet summer story",
    )

    with httpx.Client() as client:
        result = OpenAiTranslationAdapter(client).translate(request, configuration)

    assert result.translated_text.strip()
    assert result.translated_text != request.source_text
