from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from review_bot.core.logging import get_logger
from review_bot.domain.models import JobStatus, ReviewJob, ReviewResult
from review_bot.services.prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from review_bot.core.config import Settings
    from review_bot.services.gitlab_client import GitLabClient
    from review_bot.services.llm.base import LLMProvider
    from review_bot.services.template_loader import TemplateLoader

logger = get_logger(__name__)

HEADER = "> :robot: **review-bot**"


class Reviewer:
    def __init__(
        self,
        settings: Settings,
        gitlab_client: GitLabClient,
        llm_provider: LLMProvider,
        template_loader: TemplateLoader,
    ) -> None:
        self._settings = settings
        self._gitlab = gitlab_client
        self._llm = llm_provider
        self._templates = template_loader
        self._prompt_builder = PromptBuilder(max_diff_lines=settings.review.max_diff_lines)

    async def execute(self, job: ReviewJob) -> ReviewResult | None:
        corr = job.correlation_id
        log = logger.bind(correlation_id=corr, project=job.project_id, mr=job.mr_iid)

        # Handle help command
        if job.command.template == "help":
            help_text = f"{HEADER}\n\n{self._templates.format_help()}"
            self._gitlab.post_mr_comment(job.project_id, job.mr_iid, help_text)
            log.info("help posted")
            return None

        # Validate template
        template = self._templates.get(job.command.template)
        if template is None:
            available = ", ".join(f"`{n}`" for n in self._templates.available_names())
            msg = (
                f"{HEADER}: テンプレート `{job.command.template}` が見つかりません。\n"
                f"利用可能: {available}\n"
                f"使い方: `/review help`"
            )
            self._gitlab.post_mr_comment(job.project_id, job.mr_iid, msg)
            log.warning("unknown template", template=job.command.template)
            return None

        job.status = JobStatus.RUNNING
        log.info("review started", template=template.name)
        start = time.monotonic()

        try:
            mr_info = self._gitlab.get_mr_info(job.project_id, job.mr_iid)
            diffs = self._gitlab.get_mr_diffs(job.project_id, job.mr_iid)

            if len(diffs) > self._settings.review.max_files:
                diffs = diffs[: self._settings.review.max_files]
                log.warning("files truncated", count=len(diffs))

            system_prompt = self._prompt_builder.build_system_prompt(template)
            user_prompt = self._prompt_builder.build_user_prompt(
                template,
                mr_title=mr_info["title"],
                mr_description=mr_info["description"],
                target_branch=mr_info["target_branch"],
                diffs=diffs,
            )

            llm_response = await self._call_llm_with_retry(
                system_prompt,
                user_prompt,
                temperature=template.parameters.temperature,
                max_output_tokens=template.parameters.max_output_tokens,
            )

            result = ReviewResult(
                template=template.name,
                summary="",
                sections=[],
                raw_markdown=llm_response.text,
                tokens_used=(llm_response.input_tokens or 0) + (llm_response.output_tokens or 0),
            )

            comment_body = f"{HEADER} (`{template.display_name}`)\n\n{llm_response.text}"
            self._gitlab.post_mr_comment_chunked(
                job.project_id,
                job.mr_iid,
                comment_body,
                self._settings.review.comment_chunk_chars,
            )

            job.status = JobStatus.SUCCEEDED
            duration_ms = int((time.monotonic() - start) * 1000)
            log.info(
                "review completed",
                template=template.name,
                tokens=result.tokens_used,
                duration_ms=duration_ms,
            )
            return result

        except Exception as e:
            job.status = JobStatus.FAILED
            duration_ms = int((time.monotonic() - start) * 1000)
            log.error("review failed", error=str(e), duration_ms=duration_ms)
            error_msg = (
                f"{HEADER}: レビュー実行に失敗しました。\n"
                f"> - template: `{job.command.template}`\n"
                f"> - reason: {e}\n"
                f"> - correlation_id: `{corr}`\n"
                f"> 管理者に correlation_id を伝えて確認を依頼してください。"
            )
            try:
                self._gitlab.post_mr_comment(job.project_id, job.mr_iid, error_msg)
            except Exception:
                log.error("failed to post error comment")
            return None

    async def _call_llm_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float,
        max_output_tokens: int,
    ) -> "LLMResponse":  # type: ignore[name-defined]  # noqa: F821
        from review_bot.services.llm.base import LLMResponse  # noqa: F811

        max_retries = self._settings.llm.max_retries
        timeout = self._settings.llm.timeout_sec

        for attempt in range(1, max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._llm.generate(
                        system_prompt,
                        user_prompt,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                    ),
                    timeout=timeout,
                )
            except (asyncio.TimeoutError, Exception) as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"LLM call failed after {max_retries} retries: {e}"
                    ) from e
                wait = 2**attempt
                logger.warning(
                    "llm retry",
                    attempt=attempt,
                    wait=wait,
                    error=str(e),
                )
                await asyncio.sleep(wait)

        raise RuntimeError("unreachable")  # pragma: no cover
