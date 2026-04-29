from __future__ import annotations

from review_bot.domain.models import FileDiff, IssueInfo
from review_bot.services.template_loader import ReviewTemplate


class PromptBuilder:
    def __init__(self, max_diff_lines: int = 5000) -> None:
        self._max_diff_lines = max_diff_lines

    # ------------------------------------------------------------------ #
    #  MR review prompts
    # ------------------------------------------------------------------ #

    def build_system_prompt(self, template: ReviewTemplate) -> str:
        return template.system_prompt.strip()

    def build_user_prompt(
        self,
        template: ReviewTemplate,
        *,
        mr_title: str,
        mr_description: str,
        target_branch: str,
        diffs: list[FileDiff],
    ) -> str:
        parts: list[str] = []

        # MR metadata
        parts.append("## MR情報")
        parts.append(f"- **タイトル**: {mr_title}")
        parts.append(f"- **説明**: {mr_description or '(なし)'}")
        parts.append(f"- **ターゲットブランチ**: {target_branch}")
        parts.append("")

        # Checklist
        if template.checklist:
            parts.append("## レビュー観点")
            for item in template.checklist:
                parts.append(f"### {item.label}")
                for point in item.points:
                    parts.append(f"- {point}")
            parts.append("")

        # Diffs
        parts.append("## 差分")
        total_lines = 0
        for fd in diffs:
            status = self._file_status(fd)
            diff_text = self._truncate_diff(fd.diff, template.parameters.truncate_diff_strategy)
            diff_lines = diff_text.count("\n") + 1
            if total_lines + diff_lines > self._max_diff_lines:
                parts.append(f"=== FILE: {fd.new_path} ({status}) === [TRUNCATED: diff too large]")
                break
            parts.append(f"=== FILE: {fd.new_path} ({status}) ===")
            parts.append(diff_text)
            parts.append("")
            total_lines += diff_lines

        # Output format
        parts.append("## 出力フォーマット")
        parts.append(template.output_format.strip())

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    #  Issue review prompts — テンプレート駆動
    # ------------------------------------------------------------------ #

    def build_issue_system_prompt(self, template: ReviewTemplate | None = None) -> str:
        if template is not None:
            return template.system_prompt.strip()
        return _FALLBACK_ISSUE_SYSTEM_PROMPT.strip()

    def build_issue_user_prompt(
        self,
        issue: IssueInfo,
        *,
        template: ReviewTemplate | None = None,
        related_mr_titles: list[str] | None = None,
    ) -> str:
        parts: list[str] = []

        # --- Issue metadata ---
        parts.append("## Issue情報")
        parts.append(f"- **タイトル**: {issue.title}")
        parts.append(f"- **説明**:\n{issue.description or '(なし)'}")
        parts.append(f"- **ラベル**: {', '.join(issue.labels) if issue.labels else '(なし)'}")
        parts.append(f"- **状態**: {issue.state}")
        parts.append("")

        if related_mr_titles:
            parts.append("## 関連MR")
            for title in related_mr_titles:
                parts.append(f"- {title}")
            parts.append("")

        # --- レビュー観点: テンプレートから取得 ---
        if template is not None and template.checklist:
            parts.append("## レビュー観点")
            for item in template.checklist:
                parts.append(f"### {item.label}")
                for point in item.points:
                    parts.append(f"- {point}")
            parts.append("")
        else:
            parts.append("## レビュー観点")
            parts.append("- Issueのタイトルは内容を適切に要約しているか")
            parts.append("- 説明は十分に具体的か")
            parts.append("- 受け入れ基準/完了条件が明確か")
            parts.append("- 適切なラベルが付与されているか")
            parts.append("")

        # --- 出力フォーマット: テンプレートから取得 ---
        parts.append("## 出力フォーマット")
        if template is not None:
            parts.append(template.output_format.strip())
        else:
            parts.append(_FALLBACK_ISSUE_OUTPUT_FORMAT.strip())

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    #  Diff helpers
    # ------------------------------------------------------------------ #

    def _file_status(self, fd: FileDiff) -> str:
        if fd.is_new:
            return "new"
        if fd.is_deleted:
            return "deleted"
        if fd.is_renamed:
            return f"renamed from {fd.old_path}"
        return "modified"

    def _truncate_diff(self, diff: str, strategy: str) -> str:
        lines = diff.split("\n")
        max_per_file = 200

        if len(lines) <= max_per_file:
            return diff

        if strategy == "head_only":
            return "\n".join(lines[:max_per_file]) + "\n... [truncated]"

        if strategy == "per_file_head_tail":
            half = max_per_file // 2
            head = lines[:half]
            tail = lines[-half:]
            return (
                "\n".join(head)
                + f"\n... [{len(lines) - max_per_file} lines omitted] ...\n"
                + "\n".join(tail)
            )

        # summary fallback
        return "\n".join(lines[:max_per_file]) + "\n... [truncated]"


# Fallback prompts (Issueテンプレートがない場合のみ使用)
_FALLBACK_ISSUE_SYSTEM_PROMPT = """
あなたはシニアソフトウェアエンジニアであり、プロジェクトマネージャーです。
以下のIssueの内容をレビューしてください。
Issue の品質（明確さ、再現手順、受け入れ基準など）について日本語で評価してください。
"""

_FALLBACK_ISSUE_OUTPUT_FORMAT = """
## Issue レビュー結果

### 総合評価
（全体的な品質評価）

### 指摘事項
#### [重要度] 項目
- **現状**: ...
- **改善案**: ...

### 良い点
- ...
"""
