from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from review_bot.domain.models import FileDiff, JobStatus, ReviewCommand, ReviewJob
from review_bot.services.llm.base import LLMResponse
from review_bot.services.reviewer import Reviewer
from review_bot.services.template_loader import TemplateLoader


@pytest.fixture
def template_loader():
    templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
    return TemplateLoader(templates_dir)


@pytest.fixture
def reviewer(mock_settings, mock_gitlab_client, mock_llm_provider, template_loader):
    return Reviewer(mock_settings, mock_gitlab_client, mock_llm_provider, template_loader)


def make_job(template: str = "general") -> ReviewJob:
    return ReviewJob(
        project_id=42,
        mr_iid=7,
        triggered_by="testuser",
        command=ReviewCommand(template=template),
        correlation_id="test-corr-id",
    )


class TestReviewer:
    @pytest.mark.asyncio
    async def test_help_posts_template_list(self, reviewer, mock_gitlab_client):
        job = make_job("help")
        result = await reviewer.execute(job)
        assert result is None
        mock_gitlab_client.post_mr_comment.assert_called_once()
        body = mock_gitlab_client.post_mr_comment.call_args[0][2]
        assert "general" in body
        assert "security" in body
        assert "code_quality" in body
        assert "test" in body

    @pytest.mark.asyncio
    async def test_unknown_template_returns_error(self, reviewer, mock_gitlab_client):
        job = make_job("nonexistent")
        result = await reviewer.execute(job)
        assert result is None
        body = mock_gitlab_client.post_mr_comment.call_args[0][2]
        assert "見つかりません" in body

    @pytest.mark.asyncio
    async def test_successful_review_returns_result(self, reviewer, mock_gitlab_client):
        mock_gitlab_client.get_mr_diffs.return_value = [
            FileDiff(old_path="a.py", new_path="a.py", diff="+x = 1\n")
        ]
        job = make_job("general")
        result = await reviewer.execute(job)
        assert result is not None
        assert result.template == "general"
        assert result.tokens_used == 150
        assert job.status == JobStatus.SUCCEEDED
        mock_gitlab_client.post_mr_comment_chunked.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_posts_error(self, mock_settings, mock_gitlab_client, template_loader):
        failing_llm = AsyncMock()
        failing_llm.generate = AsyncMock(side_effect=RuntimeError("LLM exploded"))
        reviewer = Reviewer(mock_settings, mock_gitlab_client, failing_llm, template_loader)

        job = make_job("general")
        result = await reviewer.execute(job)
        assert result is None
        assert job.status == JobStatus.FAILED
        # Error comment should be posted
        calls = mock_gitlab_client.post_mr_comment.call_args_list
        assert any("失敗しました" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_files_truncated_when_over_max(self, reviewer, mock_gitlab_client):
        mock_gitlab_client.get_mr_diffs.return_value = [
            FileDiff(old_path=f"f{i}.py", new_path=f"f{i}.py", diff=f"+line{i}\n")
            for i in range(100)
        ]
        job = make_job("general")
        result = await reviewer.execute(job)
        assert result is not None

    @pytest.mark.asyncio
    async def test_review_with_each_template(self, reviewer, mock_gitlab_client):
        for template_name in ["general", "code_quality", "security", "test"]:
            mock_gitlab_client.reset_mock()
            mock_gitlab_client.get_mr_diffs.return_value = [
                FileDiff(old_path="x.py", new_path="x.py", diff="+pass\n")
            ]
            job = make_job(template_name)
            result = await reviewer.execute(job)
            assert result is not None
            assert result.template == template_name
