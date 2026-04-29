from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from review_bot.core.logging import get_logger

logger = get_logger(__name__)


class ChecklistItem(BaseModel):
    id: str
    label: str
    points: list[str]


class TemplateParameters(BaseModel):
    temperature: float = 0.2
    max_output_tokens: int = 4096
    include_full_diff: bool = True
    truncate_diff_strategy: str = "per_file_head_tail"


class ReviewTemplate(BaseModel):
    name: str
    display_name: str
    description: str
    version: int = 1
    type: str = "mr"  # "mr" or "issue"
    system_prompt: str
    checklist: list[ChecklistItem] = Field(default_factory=list)
    output_format: str
    parameters: TemplateParameters = Field(default_factory=TemplateParameters)
    # Issue テンプレートの自動選択用キーワード (type=issue のみ)
    keywords: list[str] = Field(default_factory=list)


class TemplateLoader:
    def __init__(self, templates_dir: str | Path) -> None:
        self._dir = Path(templates_dir)
        self._templates: dict[str, ReviewTemplate] = {}
        self._mr_templates: dict[str, ReviewTemplate] = {}
        self._issue_templates: dict[str, ReviewTemplate] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self._dir.exists():
            raise RuntimeError(f"Templates directory not found: {self._dir}")

        for path in sorted(self._dir.glob("*.yaml")):
            try:
                with open(path, encoding="utf-8") as f:
                    data: dict[str, Any] = yaml.safe_load(f) or {}
                template = ReviewTemplate(**data)
                if template.name != path.stem:
                    logger.warning(
                        "template name mismatch",
                        file=str(path),
                        name=template.name,
                        stem=path.stem,
                    )
                self._templates[template.name] = template

                if template.type == "issue":
                    self._issue_templates[template.name] = template
                else:
                    self._mr_templates[template.name] = template

                logger.info("template loaded", name=template.name, type=template.type)
            except Exception as e:
                raise RuntimeError(f"Failed to load template {path}: {e}") from e

        if not self._templates:
            raise RuntimeError(f"No templates found in {self._dir}")

    def get(self, name: str) -> ReviewTemplate | None:
        return self._templates.get(name)

    def list_templates(self) -> list[ReviewTemplate]:
        return list(self._templates.values())

    def available_names(self) -> list[str]:
        """MRテンプレートの名前一覧 (/review <name> で使用可能なもの)。"""
        return list(self._mr_templates.keys())

    def available_issue_names(self) -> list[str]:
        return list(self._issue_templates.keys())

    def match_issue_template(self, title: str, description: str, labels: list[str]) -> ReviewTemplate | None:
        """Issue の内容からキーワードマッチで最適なIssueテンプレートを選択する。

        各テンプレートの keywords を照合し、最もマッチ数が多いテンプレートを返す。
        マッチがなければ issue_general を返す。issue_general もなければ None。
        """
        text = f"{title} {description} {' '.join(labels)}".lower()
        best: ReviewTemplate | None = None
        best_score = 0

        for tmpl in self._issue_templates.values():
            if not tmpl.keywords:
                continue
            score = sum(1 for kw in tmpl.keywords if kw.lower() in text)
            if score > best_score:
                best_score = score
                best = tmpl

        if best is not None:
            return best

        # Fallback to issue_general
        return self._issue_templates.get("issue_general")

    def format_help(self) -> str:
        lines = ["**利用可能なレビューテンプレート:**", ""]

        mr_templates = [t for t in self._templates.values() if t.type == "mr"]
        issue_templates = [t for t in self._templates.values() if t.type == "issue"]

        if mr_templates:
            lines.append("**MR レビュー** (MRコメントで使用):")
            for t in mr_templates:
                lines.append(f"- `/review {t.name}` — {t.display_name}: {t.description}")
            lines.append("")

        if issue_templates:
            lines.append("**Issue レビュー** (Issueコメントで使用):")
            lines.append("Issueの内容に応じて自動的に最適なテンプレートが選択されます。")
            for t in issue_templates:
                lines.append(f"- `{t.name}` — {t.display_name}: {t.description}")
            lines.append("")

        lines.append("テンプレート未指定時は `general` (MR) / 自動選択 (Issue) が使用されます。")
        return "\n".join(lines)
