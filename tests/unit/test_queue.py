from unittest.mock import AsyncMock, MagicMock

import pytest

from review_bot.domain.models import IssueInfo, ReviewCommand
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
    reviewer.execute_issue_review = AsyncMock(return_value=None)
    reviewer._gitlab = MagicMock()
    reviewer._gitlab.post_mr_comment = MagicMock()
    reviewer._gitlab.post_issue_comment = MagicMock()
    reviewer._gitlab.post_issue_comment_chunked = MagicMock()
    reviewer._gitlab.get_issue_related_mrs = MagicMock(return_value=[])
    reviewer._gitlab.get_issue_info = MagicMock(
        return_value=IssueInfo(
            project_id=42,
            issue_iid=5,
            title="Test Issue",
            description="Some description",
            labels=["bug"],
            state="opened",
        )
    )
    reviewer._gitlab.get_mr_info = MagicMock(
        return_value={
            "title": "Test MR",
            "description": "",
            "target_branch": "main",
            "source_branch": "feature/test",
        }
    )
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
    async def test_issue_review_reviews_issue_itself(self, mock_reviewer):
        """Issue コメントの /review ではIssue自体もレビューされる"""
        payload = make_issue_payload()
        cmd = ReviewCommand(template="general")
        mock_reviewer._gitlab.get_issue_related_mrs.return_value = []
        await enqueue_review(payload, cmd, mock_reviewer, from_issue=True)
        # Issue自体のレビューが呼ばれる
        mock_reviewer.execute_issue_review.assert_called_once()
        call_args = mock_reviewer.execute_issue_review.call_args
        issue_info = call_args[0][0]
        assert issue_info.issue_iid == 5
        assert issue_info.title == "Test Issue"

    @pytest.mark.asyncio
    async def test_issue_review_with_related_mr(self, mock_reviewer):
        """Issue + 関連MRの両方がレビューされる"""
        payload = make_issue_payload()
        cmd = ReviewCommand(template="general")
        mock_reviewer._gitlab.get_issue_related_mrs.return_value = [
            {"iid": 10, "project_id": 42}
        ]
        job = await enqueue_review(payload, cmd, mock_reviewer, from_issue=True)
        # Issue自体のレビュー
        mock_reviewer.execute_issue_review.assert_called_once()
        # 関連MRのレビュー
        mock_reviewer.execute.assert_called_once()
        assert job is not None
        assert job.mr_iid == 10

    @pytest.mark.asyncio
    async def test_issue_review_multiple_related_mrs(self, mock_reviewer):
        """複数の関連MRがある場合、全てレビューされる"""
        payload = make_issue_payload()
        cmd = ReviewCommand(template="general")
        mock_reviewer._gitlab.get_issue_related_mrs.return_value = [
            {"iid": 10, "project_id": 42},
            {"iid": 11, "project_id": 42},
        ]
        job = await enqueue_review(payload, cmd, mock_reviewer, from_issue=True)
        # Issue自体 + MR2件
        mock_reviewer.execute_issue_review.assert_called_once()
        assert mock_reviewer.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_issue_review_get_info_failure_still_reviews_mrs(self, mock_reviewer):
        """Issue情報取得に失敗しても関連MRはレビューされる"""
        payload = make_issue_payload()
        cmd = ReviewCommand(template="general")
        mock_reviewer._gitlab.get_issue_info.side_effect = RuntimeError("API error")
        mock_reviewer._gitlab.get_issue_related_mrs.return_value = [
            {"iid": 10, "project_id": 42}
        ]
        job = await enqueue_review(payload, cmd, mock_reviewer, from_issue=True)
        # Issue自体のレビューは呼ばれない（info取得失敗）
        mock_reviewer.execute_issue_review.assert_not_called()
        # MRレビューは実行される
        mock_reviewer.execute.assert_called_once()
        assert job is not None
