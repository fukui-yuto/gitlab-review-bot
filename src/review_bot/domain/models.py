from dataclasses import dataclass, field
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ReviewCommand:
    template: str
    extra_args: dict[str, str] = field(default_factory=dict)


@dataclass
class ReviewJob:
    project_id: int
    mr_iid: int
    triggered_by: str
    command: ReviewCommand
    correlation_id: str
    status: JobStatus = JobStatus.QUEUED


@dataclass
class FileDiff:
    old_path: str
    new_path: str
    diff: str
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False


@dataclass
class ReviewResult:
    template: str
    summary: str
    sections: list[dict[str, str]]
    raw_markdown: str
    tokens_used: int | None = None
