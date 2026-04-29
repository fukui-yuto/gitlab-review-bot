from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from review_bot.core.logging import generate_correlation_id, get_logger
from review_bot.domain.models import JobStatus, ReviewCommand, ReviewJob

if TYPE_CHECKING:
    from review_bot.services.reviewer import Reviewer

logger = get_logger(__name__)

_queue: asyncio.Queue[ReviewJob] = asyncio.Queue()
_active_jobs: set[str] = set()


def _job_key(project_id: int, mr_iid: int) -> str:
    return f"{project_id}:{mr_iid}"


async def enqueue_review(
    payload: dict,
    command: ReviewCommand,
    reviewer: "Reviewer",
    *,
    from_issue: bool = False,
) -> ReviewJob | None:
    project_id = payload.get("project", {}).get("id", 0)
    user = payload.get("user", {}).get("username", "unknown")

    if from_issue:
        return await _handle_issue_review(payload, command, reviewer, project_id, user)

    mr = payload.get("merge_request", {})
    mr_iid = mr.get("iid", 0)
    return await _run_mr_review(project_id, mr_iid, user, command, reviewer)


async def _handle_issue_review(
    payload: dict,
    command: ReviewCommand,
    reviewer: "Reviewer",
    project_id: int,
    user: str,
) -> ReviewJob | None:
    from review_bot.services.reviewer import HEADER

    issue = payload.get("issue", {})
    issue_iid = issue.get("iid", 0)

    # Find related open MRs for this issue
    try:
        related_mrs = reviewer._gitlab.get_issue_related_mrs(project_id, issue_iid)
    except Exception as e:
        logger.warning("failed to get issue related MRs", error=str(e))
        # Fallback: try to find MRs referencing this issue
        related_mrs = []

    if not related_mrs:
        reviewer._gitlab.post_issue_comment(
            project_id,
            issue_iid,
            f"{HEADER}: この Issue に関連するオープンな MR が見つかりませんでした。\n"
            f"MR のコメント欄で `/review` を実行するか、Issue に MR を関連付けてください。",
        )
        return None

    # Review each related MR
    last_job = None
    for mr_ref in related_mrs:
        mr_iid = mr_ref["iid"]
        reviewer._gitlab.post_issue_comment(
            project_id,
            issue_iid,
            f"{HEADER}: MR !{mr_iid} のレビューを開始します。",
        )
        job = await _run_mr_review(project_id, mr_iid, user, command, reviewer)
        if job:
            last_job = job
    return last_job


async def _run_mr_review(
    project_id: int,
    mr_iid: int,
    user: str,
    command: ReviewCommand,
    reviewer: "Reviewer",
) -> ReviewJob | None:
    from review_bot.services.reviewer import HEADER

    key = _job_key(project_id, mr_iid)

    if key in _active_jobs:
        logger.info("duplicate job skipped", key=key)
        try:
            reviewer._gitlab.post_mr_comment(
                project_id,
                mr_iid,
                f"{HEADER}: このMRで既にレビューが実行中です。完了後に再度お試しください。",
            )
        except Exception:
            pass
        return None

    job = ReviewJob(
        project_id=project_id,
        mr_iid=mr_iid,
        triggered_by=user,
        command=command,
        correlation_id=generate_correlation_id(),
    )

    _active_jobs.add(key)
    try:
        job.status = JobStatus.RUNNING
        await reviewer.execute(job)
    finally:
        _active_jobs.discard(key)

    return job
