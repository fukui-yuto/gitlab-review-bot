import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Set test environment variables before any imports
os.environ.setdefault("GITLAB_TOKEN", "test-token")
os.environ.setdefault("GITLAB_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")


@pytest.fixture
def templates_dir() -> Path:
    return Path(__file__).parent.parent / "config" / "templates"


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "integration" / "fixtures"


@pytest.fixture
def mock_settings():
    from review_bot.core.config import load_settings

    return load_settings(Path(__file__).parent.parent / "config" / "settings.example.yaml")


@pytest.fixture
def mock_gitlab_client():
    client = MagicMock()
    client.verify_connection = MagicMock()
    client.get_mr_info = MagicMock(
        return_value={
            "title": "Test MR",
            "description": "Test description",
            "target_branch": "main",
            "source_branch": "feature/test",
        }
    )
    client.get_mr_diffs = MagicMock(return_value=[])
    client.post_mr_comment = MagicMock()
    client.post_mr_comment_chunked = MagicMock()
    # Issue support
    client.get_issue_related_mrs = MagicMock(return_value=[])
    client.post_issue_comment = MagicMock()
    return client


@pytest.fixture
def mock_llm_provider():
    from review_bot.services.llm.base import LLMResponse

    provider = AsyncMock()
    provider.generate = AsyncMock(
        return_value=LLMResponse(
            text="## 概要\nテストレビュー結果です。\n## Good Points\n- よくできています",
            input_tokens=100,
            output_tokens=50,
        )
    )
    return provider
