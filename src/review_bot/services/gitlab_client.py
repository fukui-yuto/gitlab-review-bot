from __future__ import annotations

from typing import TYPE_CHECKING, Any

import gitlab

from review_bot.core.logging import get_logger
from review_bot.domain.models import FileDiff

if TYPE_CHECKING:
    from review_bot.core.config import Settings

logger = get_logger(__name__)


class GitLabClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        ssl_verify: bool | str = settings.gitlab.ssl_verify
        if settings.gitlab.ca_bundle:
            ssl_verify = settings.gitlab.ca_bundle
        self._gl = gitlab.Gitlab(
            url=settings.gitlab.url,
            private_token=settings.gitlab.token,
            ssl_verify=ssl_verify,
        )

    def verify_connection(self) -> None:
        self._gl.auth()
        logger.info("gitlab connection verified", user=self._gl.user.username)  # type: ignore[union-attr]

    def get_mr_info(self, project_id: int, mr_iid: int) -> dict[str, Any]:
        project = self._gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)
        return {
            "title": mr.title,
            "description": mr.description or "",
            "target_branch": mr.target_branch,
            "source_branch": mr.source_branch,
        }

    def get_mr_diffs(self, project_id: int, mr_iid: int) -> list[FileDiff]:
        project = self._gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)
        changes = mr.changes()
        diffs: list[FileDiff] = []
        for change in changes.get("changes", []):
            diffs.append(
                FileDiff(
                    old_path=change.get("old_path", ""),
                    new_path=change.get("new_path", ""),
                    diff=change.get("diff", ""),
                    is_new=change.get("new_file", False),
                    is_deleted=change.get("deleted_file", False),
                    is_renamed=change.get("renamed_file", False),
                )
            )
        return diffs

    def post_mr_comment(self, project_id: int, mr_iid: int, body: str) -> None:
        project = self._gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)
        mr.notes.create({"body": body})
        logger.info("comment posted", project_id=project_id, mr_iid=mr_iid)

    def post_mr_comment_chunked(
        self, project_id: int, mr_iid: int, body: str, chunk_chars: int = 3800
    ) -> None:
        if len(body) <= chunk_chars:
            self.post_mr_comment(project_id, mr_iid, body)
            return

        chunks = self._split_chunks(body, chunk_chars)
        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            header = f"### Part {i}/{total}\n\n" if total > 1 else ""
            self.post_mr_comment(project_id, mr_iid, header + chunk)

    def get_issue_related_mrs(self, project_id: int, issue_iid: int) -> list[dict[str, int]]:
        project = self._gl.projects.get(project_id)
        issue = project.issues.get(issue_iid)
        mrs = issue.related_merge_requests()
        result = []
        for mr in mrs:
            if mr.get("state") == "opened":
                result.append({"iid": mr["iid"], "project_id": project_id})
        logger.info(
            "issue related MRs",
            project_id=project_id,
            issue_iid=issue_iid,
            count=len(result),
        )
        return result

    def post_issue_comment(self, project_id: int, issue_iid: int, body: str) -> None:
        project = self._gl.projects.get(project_id)
        issue = project.issues.get(issue_iid)
        issue.notes.create({"body": body})
        logger.info("issue comment posted", project_id=project_id, issue_iid=issue_iid)

    def post_issue_comment_chunked(
        self, project_id: int, issue_iid: int, body: str, chunk_chars: int = 3800
    ) -> None:
        if len(body) <= chunk_chars:
            self.post_issue_comment(project_id, issue_iid, body)
            return

        chunks = self._split_chunks(body, chunk_chars)
        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            header = f"### Part {i}/{total}\n\n" if total > 1 else ""
            self.post_issue_comment(project_id, issue_iid, header + chunk)

    @staticmethod
    def _split_chunks(body: str, chunk_chars: int) -> list[str]:
        chunks: list[str] = []
        current = ""
        for line in body.split("\n"):
            if len(current) + len(line) + 1 > chunk_chars and current:
                chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)
        return chunks
