import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from review_bot.api.webhook import init_webhook, router
from review_bot.core.config import load_settings
from review_bot.domain.command import parse_review_command


@pytest.fixture
def settings():
    import os

    os.environ["GITLAB_WEBHOOK_SECRET"] = "test-secret"
    return load_settings(Path(__file__).parent.parent.parent / "config" / "settings.example.yaml")


@pytest.fixture
def mock_reviewer():
    reviewer = AsyncMock()
    reviewer.execute = AsyncMock(return_value=None)
    reviewer._gitlab = MagicMock()
    reviewer._gitlab.post_mr_comment = MagicMock()
    reviewer._templates = MagicMock()
    return reviewer


@pytest.fixture
def app(settings, mock_reviewer):
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(router)
    init_webhook(settings, mock_reviewer)
    return test_app


@pytest.fixture
def mr_payload(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "webhook_note_mr.json") as f:
        return json.load(f)


@pytest.fixture
def issue_payload(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "webhook_note_issue.json") as f:
        return json.load(f)


class TestWebhookEndpoint:
    @pytest.mark.asyncio
    async def test_valid_mr_webhook(self, app, mr_payload):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhook/gitlab",
                json=mr_payload,
                headers={"X-Gitlab-Token": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_valid_issue_webhook(self, app, issue_payload):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhook/gitlab",
                json=issue_payload,
                headers={"X-Gitlab-Token": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, app, mr_payload):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhook/gitlab",
                json=mr_payload,
                headers={"X-Gitlab-Token": "wrong-secret"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, app, mr_payload):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhook/gitlab",
                json=mr_payload,
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_note_event_ignored(self, app):
        payload = {"object_kind": "push"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhook/gitlab",
                json=payload,
                headers={"X-Gitlab-Token": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_note_without_command_ignored(self, app, mr_payload):
        mr_payload["object_attributes"]["note"] = "just a regular comment"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhook/gitlab",
                json=mr_payload,
                headers={"X-Gitlab-Token": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "no-command"

    @pytest.mark.asyncio
    async def test_review_with_template(self, app, mr_payload):
        mr_payload["object_attributes"]["note"] = "/review security"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhook/gitlab",
                json=mr_payload,
                headers={"X-Gitlab-Token": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"


class TestReviewerIntegration:
    @pytest.mark.asyncio
    async def test_help_command(self, mock_settings, mock_gitlab_client, mock_llm_provider):
        from review_bot.domain.models import ReviewCommand, ReviewJob
        from review_bot.services.reviewer import Reviewer
        from review_bot.services.template_loader import TemplateLoader

        templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        loader = TemplateLoader(templates_dir)
        reviewer = Reviewer(mock_settings, mock_gitlab_client, mock_llm_provider, loader)

        job = ReviewJob(
            project_id=42,
            mr_iid=7,
            triggered_by="testuser",
            command=ReviewCommand(template="help"),
            correlation_id="test-corr-id",
        )
        result = await reviewer.execute(job)
        assert result is None
        mock_gitlab_client.post_mr_comment.assert_called_once()
        call_args = mock_gitlab_client.post_mr_comment.call_args[0]
        assert "利用可能なレビューテンプレート" in call_args[2]

    @pytest.mark.asyncio
    async def test_unknown_template(self, mock_settings, mock_gitlab_client, mock_llm_provider):
        from review_bot.domain.models import ReviewCommand, ReviewJob
        from review_bot.services.reviewer import Reviewer
        from review_bot.services.template_loader import TemplateLoader

        templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        loader = TemplateLoader(templates_dir)
        reviewer = Reviewer(mock_settings, mock_gitlab_client, mock_llm_provider, loader)

        job = ReviewJob(
            project_id=42,
            mr_iid=7,
            triggered_by="testuser",
            command=ReviewCommand(template="nonexistent"),
            correlation_id="test-corr-id",
        )
        result = await reviewer.execute(job)
        assert result is None
        mock_gitlab_client.post_mr_comment.assert_called_once()
        call_args = mock_gitlab_client.post_mr_comment.call_args[0]
        assert "見つかりません" in call_args[2]

    @pytest.mark.asyncio
    async def test_successful_review(self, mock_settings, mock_gitlab_client, mock_llm_provider):
        from review_bot.domain.models import FileDiff, ReviewCommand, ReviewJob
        from review_bot.services.reviewer import Reviewer
        from review_bot.services.template_loader import TemplateLoader

        mock_gitlab_client.get_mr_diffs.return_value = [
            FileDiff(
                old_path="test.py",
                new_path="test.py",
                diff="+print('hello')\n",
            )
        ]

        templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        loader = TemplateLoader(templates_dir)
        reviewer = Reviewer(mock_settings, mock_gitlab_client, mock_llm_provider, loader)

        job = ReviewJob(
            project_id=42,
            mr_iid=7,
            triggered_by="testuser",
            command=ReviewCommand(template="general"),
            correlation_id="test-corr-id",
        )
        result = await reviewer.execute(job)
        assert result is not None
        assert result.template == "general"
        assert result.tokens_used == 150
        mock_gitlab_client.post_mr_comment_chunked.assert_called_once()
