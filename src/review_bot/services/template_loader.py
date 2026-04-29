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
    system_prompt: str
    checklist: list[ChecklistItem] = Field(default_factory=list)
    output_format: str
    parameters: TemplateParameters = Field(default_factory=TemplateParameters)


class TemplateLoader:
    def __init__(self, templates_dir: str | Path) -> None:
        self._dir = Path(templates_dir)
        self._templates: dict[str, ReviewTemplate] = {}
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
                logger.info("template loaded", name=template.name)
            except Exception as e:
                raise RuntimeError(f"Failed to load template {path}: {e}") from e

        if not self._templates:
            raise RuntimeError(f"No templates found in {self._dir}")

    def get(self, name: str) -> ReviewTemplate | None:
        return self._templates.get(name)

    def list_templates(self) -> list[ReviewTemplate]:
        return list(self._templates.values())

    def available_names(self) -> list[str]:
        return list(self._templates.keys())

    def format_help(self) -> str:
        lines = ["**利用可能なレビューテンプレート:**", ""]
        for t in self._templates.values():
            lines.append(f"- `/review {t.name}` — {t.display_name}: {t.description}")
        lines.append("")
        lines.append("テンプレート未指定時は `general` が使用されます。")
        return "\n".join(lines)
