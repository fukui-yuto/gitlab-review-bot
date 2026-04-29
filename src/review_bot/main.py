from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from review_bot.api.webhook import init_webhook, router as webhook_router
from review_bot.core.config import load_settings
from review_bot.core.logging import get_logger, setup_logging
from review_bot.services.gitlab_client import GitLabClient
from review_bot.services.llm.factory import build_llm_provider
from review_bot.services.reviewer import Reviewer
from review_bot.services.template_loader import TemplateLoader


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger = get_logger("startup")

    settings = load_settings()
    setup_logging(settings.app.log_level)

    logger.info("loading templates", dir=settings.review.templates_dir)
    template_loader = TemplateLoader(settings.review.templates_dir)
    logger.info("templates loaded", count=len(template_loader.available_names()))

    logger.info("connecting to gitlab", url=settings.gitlab.url)
    gitlab_client = GitLabClient(settings)
    gitlab_client.verify_connection()

    logger.info("initializing llm provider", provider=settings.llm.provider)
    llm_provider = build_llm_provider(settings)

    reviewer = Reviewer(settings, gitlab_client, llm_provider, template_loader)
    init_webhook(settings, reviewer)

    logger.info("review-bot started", port=settings.app.port)
    yield
    logger.info("review-bot shutting down")


app = FastAPI(title="GitLab Review Bot", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
