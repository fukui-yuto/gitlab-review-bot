from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"


class GitLabConfig(BaseModel):
    url: str = "http://localhost:8929"
    webhook_secret_env: str = "GITLAB_WEBHOOK_SECRET"
    ssl_verify: bool = True
    ca_bundle: str | None = None

    @property
    def token(self) -> str:
        val = os.environ.get("GITLAB_TOKEN", "")
        if not val:
            raise RuntimeError("GITLAB_TOKEN environment variable is not set")
        return val

    @property
    def webhook_secret(self) -> str:
        return os.environ.get(self.webhook_secret_env, "")


class GeminiConfig(BaseModel):
    model: str = "gemini-2.5-flash"
    api_key_env: str = "GEMINI_API_KEY"

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")


class OpenAIConfig(BaseModel):
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")


class LLMConfig(BaseModel):
    provider: str = "gemini"
    timeout_sec: int = 60
    max_retries: int = 3
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)

    @property
    def effective_provider(self) -> str:
        """LLM_PROVIDER env var overrides YAML config."""
        return os.environ.get("LLM_PROVIDER", self.provider)


class ReviewConfig(BaseModel):
    default_template: str = "general"
    templates_dir: str = "config/templates"
    max_diff_lines: int = 5000
    max_files: int = 50
    comment_chunk_chars: int = 3800


class NetworkConfig(BaseModel):
    http_proxy_env: str = "HTTP_PROXY"
    https_proxy_env: str = "HTTPS_PROXY"
    no_proxy_env: str = "NO_PROXY"


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    gitlab: GitLabConfig = Field(default_factory=GitLabConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)


def load_settings(config_path: str | Path | None = None) -> Settings:
    data: dict[str, Any] = {}
    if config_path is None:
        for candidate in ["config/settings.yaml", "config/settings.example.yaml"]:
            if Path(candidate).exists():
                config_path = candidate
                break

    if config_path and Path(config_path).exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    return Settings(**data)
