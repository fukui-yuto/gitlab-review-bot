from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from review_bot.core.security import verify_gitlab_signature
from review_bot.domain.command import parse_review_command
from review_bot.worker.queue import enqueue_review

if TYPE_CHECKING:
    from review_bot.core.config import Settings
    from review_bot.services.reviewer import Reviewer

router = APIRouter(prefix="/api/v1/webhook")

_reviewer: Reviewer | None = None
_settings: Settings | None = None


def init_webhook(settings: "Settings", reviewer: "Reviewer") -> None:
    global _reviewer, _settings
    _reviewer = reviewer
    _settings = settings


@router.post("/gitlab")
async def gitlab_webhook(req: Request, bg: BackgroundTasks) -> dict[str, str]:
    if _settings is None or _reviewer is None:
        raise HTTPException(status_code=503, detail="not initialized")

    token = req.headers.get("X-Gitlab-Token", "")
    if not verify_gitlab_signature(token, _settings.gitlab.webhook_secret):
        raise HTTPException(status_code=401, detail="invalid token")

    payload = await req.json()

    if payload.get("object_kind") != "note":
        return {"status": "ignored"}

    note = payload.get("object_attributes", {}).get("note", "")
    cmd = parse_review_command(note)
    if cmd is None:
        return {"status": "no-command"}

    # Determine context: MR comment or Issue comment
    noteable_type = payload.get("object_attributes", {}).get("noteable_type", "")
    if noteable_type == "MergeRequest":
        bg.add_task(enqueue_review, payload=payload, command=cmd, reviewer=_reviewer)
    elif noteable_type == "Issue":
        bg.add_task(
            enqueue_review, payload=payload, command=cmd, reviewer=_reviewer, from_issue=True
        )
    else:
        return {"status": "ignored"}

    return {"status": "accepted"}
