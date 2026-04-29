import os
from pathlib import Path

import pytest

from review_bot.core.config import Settings, load_settings


class TestConfig:
    def test_load_example_settings(self):
        path = Path(__file__).parent.parent.parent / "config" / "settings.example.yaml"
        settings = load_settings(path)
        assert settings.app.port == 8080
        assert settings.llm.provider == "gemini"
        assert settings.review.default_template == "general"

    def test_default_settings(self):
        settings = Settings()
        assert settings.app.host == "0.0.0.0"
        assert settings.app.port == 8080
        assert settings.llm.max_retries == 3

    def test_gitlab_token_from_env(self):
        os.environ["GITLAB_TOKEN"] = "test-token-123"
        settings = Settings()
        assert settings.gitlab.token == "test-token-123"

    def test_gitlab_token_missing_raises(self):
        orig = os.environ.pop("GITLAB_TOKEN", None)
        try:
            settings = Settings()
            with pytest.raises(RuntimeError, match="GITLAB_TOKEN"):
                _ = settings.gitlab.token
        finally:
            if orig:
                os.environ["GITLAB_TOKEN"] = orig

    def test_webhook_secret(self):
        os.environ["GITLAB_WEBHOOK_SECRET"] = "my-secret"
        settings = Settings()
        assert settings.gitlab.webhook_secret == "my-secret"

    def test_load_nonexistent_file(self):
        settings = load_settings("/nonexistent/path.yaml")
        assert settings.app.port == 8080  # defaults

    def test_review_config_defaults(self):
        settings = Settings()
        assert settings.review.max_diff_lines == 5000
        assert settings.review.max_files == 50
        assert settings.review.comment_chunk_chars == 3800
