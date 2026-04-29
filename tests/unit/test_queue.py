from unittest.mock import AsyncMock, MagicMock

import pytest

from review_bot.domain.models import ReviewCommand
from review_bot.worker.queue import _active_jobs, enqueue_review


def make_mr_payload(project_id: int = 42, mr_iid: int = 7) -> dict:
    return {
        "object_kind": "note",
        "user": {"username": "testuser"},
        "project": {"id": project_id},
        "object_attributes": {"note": "/review", "noteable_type": "MergeRequest"},
        "merge_request": {"iid": mr_iid, "title": "Test"},
    }


def make_issue_payload(project_id: int = 42, issue_iid: int = 5) -> dict:
    return {
        "object_kind": "note",
        "user": {"username": "testuser"},
        "project": {"id": project_id},
        "object_attributes": {"note": "/review", "noteable_type": "Issue"},
        "issue": {"iid": issue_iid, "title": "Test Issue"},
    }


@pytest.fixture(autouse=True)
def clear_active_jobs():
    _active_jobs.clear()
    yield
    _active_jobs.clear()


@pytest.fixture
def mock_reviewer():
    reviewer = AsyncMock()
    reviewer.execute = AsyncMock(return_value=None)
    reviewer._gitlab = MagicMock()
    reviewer._gitlab.post_mr_comment = MagicMock()
    reviewer._gitlab.post_issue_comment = MagicMock()
    reviewer._gitlab.get_issue_related_mrs = MagicMock(return_value=[])
    return reviewer


class TestEnqueueReview:
    @pytest.mark.asyncio
    async def test_mr_review_enqueued(self, mock_reviewer):
        payload = make_mr_payload()
        cmd = ReviewCommand(template="general")
        job = await enqueue_review(payload, cmd, mock_reviewer)
        assert job is not None
        assert job.project_id == 42
        assert job.mr_iid == 7
        mock_reviewer.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_mr_skipped(self, mock_reviewer):
        _active_jobs.add("42:7")
        payload = make_mr_payload()
        cmd = ReviewCommand(template="general")
        job = await enqueue_review(payload, cmd, mock_reviewer)
        assert job is None
        mock_reviewer.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_job_cleared_after_completion(self, mock_reviewer):
        payload = make_mr_payload()
        cmd = ReviewCommand(template="general")
        await enqueue_review(payload, cmd, mock_reviewer)
        assert "42:7" not in _active_jobs

    @pytest.mark.asyncio
    async def test_issue_review_no_related_mrs(self, mock_reviewer):
        payload = make_issue_payload()
        cmd = ReviewCommand(template="general")
        mock_reviewer._gitlab.get_issue_related_mrs.return_value = []
        job = await enqueue_review(payload, cmd, mock_reviewer, from_issue=True)
        assert job is None
        mock_reviewer._gitlab.post_issue_comment.assert_called_once()
        body = mock_reviewer._gitlab.post_issue_comment.call_args[0][2]
        assert "見つかりませんでした" in body

    @pytest.mark.asyncio
    async def test_issue_review_with_related_mr(self, mock_reviewer):
        payload = make_issue_payload()
        cmd = ReviewCommand(template="general")
        mock_reviewer._gitlab.get_issue_related_mrs.return_value = [
            {"iid": 10, "project_id": 42}
        ]
        job = await enqueue_review(payload, cmd, mock_reviewer, from_issue=True)
        assert job is not None
        assert job.mr_iid == 10
        mock_reviewer.execute.assert_called_once()
