from pathlib import Path

from review_bot.domain.models import FileDiff, IssueInfo
from review_bot.services.prompt_builder import PromptBuilder
from review_bot.services.template_loader import TemplateLoader


class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder(max_diff_lines=5000)
        templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        self.loader = TemplateLoader(templates_dir)
        self.template = self.loader.get("general")
        assert self.template is not None

    def test_build_system_prompt(self):
        prompt = self.builder.build_system_prompt(self.template)
        assert "シニアソフトウェアエンジニア" in prompt

    def test_build_user_prompt_basic(self):
        diffs = [
            FileDiff(
                old_path="src/foo.py",
                new_path="src/foo.py",
                diff="@@ -1,3 +1,5 @@\n+import os\n def hello():\n-    pass\n+    print('hello')\n",
            )
        ]
        prompt = self.builder.build_user_prompt(
            self.template,
            mr_title="Test MR",
            mr_description="Test description",
            target_branch="main",
            diffs=diffs,
        )
        assert "Test MR" in prompt
        assert "src/foo.py" in prompt
        assert "modified" in prompt
        assert "レビュー観点" in prompt

    def test_build_user_prompt_new_file(self):
        diffs = [
            FileDiff(
                old_path="",
                new_path="src/new.py",
                diff="+print('new file')\n",
                is_new=True,
            )
        ]
        prompt = self.builder.build_user_prompt(
            self.template,
            mr_title="Add new file",
            mr_description="",
            target_branch="main",
            diffs=diffs,
        )
        assert "new" in prompt.lower()

    def test_build_user_prompt_deleted_file(self):
        diffs = [
            FileDiff(
                old_path="src/old.py",
                new_path="src/old.py",
                diff="-print('deleted')\n",
                is_deleted=True,
            )
        ]
        prompt = self.builder.build_user_prompt(
            self.template,
            mr_title="Remove old file",
            mr_description="Cleanup",
            target_branch="main",
            diffs=diffs,
        )
        assert "deleted" in prompt

    def test_build_user_prompt_renamed_file(self):
        diffs = [
            FileDiff(
                old_path="src/old_name.py",
                new_path="src/new_name.py",
                diff="",
                is_renamed=True,
            )
        ]
        prompt = self.builder.build_user_prompt(
            self.template,
            mr_title="Rename file",
            mr_description="",
            target_branch="main",
            diffs=diffs,
        )
        assert "renamed from src/old_name.py" in prompt

    def test_diff_truncation_head_only(self):
        long_diff = "\n".join([f"+line {i}" for i in range(300)])
        diffs = [FileDiff(old_path="big.py", new_path="big.py", diff=long_diff)]
        prompt = self.builder.build_user_prompt(
            self.template,
            mr_title="Big change",
            mr_description="",
            target_branch="main",
            diffs=diffs,
        )
        # Should contain the diff (with truncation since > 200 lines)
        assert "big.py" in prompt

    def test_max_diff_lines_limit(self):
        builder = PromptBuilder(max_diff_lines=10)
        diffs = [
            FileDiff(
                old_path=f"file{i}.py",
                new_path=f"file{i}.py",
                diff="\n".join([f"+line {j}" for j in range(20)]),
            )
            for i in range(5)
        ]
        prompt = builder.build_user_prompt(
            self.template,
            mr_title="Many files",
            mr_description="",
            target_branch="main",
            diffs=diffs,
        )
        assert "TRUNCATED" in prompt

    def test_empty_description(self):
        prompt = self.builder.build_user_prompt(
            self.template,
            mr_title="No desc",
            mr_description="",
            target_branch="main",
            diffs=[],
        )
        assert "(なし)" in prompt

    def test_output_format_included(self):
        prompt = self.builder.build_user_prompt(
            self.template,
            mr_title="Test",
            mr_description="",
            target_branch="main",
            diffs=[],
        )
        assert "出力フォーマット" in prompt
        assert "概要" in prompt

    def test_issue_system_prompt(self):
        prompt = self.builder.build_issue_system_prompt()
        assert "Issue" in prompt
        assert "レビュー" in prompt

    def test_issue_user_prompt_basic(self):
        issue = IssueInfo(
            project_id=42,
            issue_iid=5,
            title="ログイン画面のバグ",
            description="パスワード入力時にエラーが発生する",
            labels=["bug", "urgent"],
            state="opened",
        )
        prompt = self.builder.build_issue_user_prompt(issue)
        assert "ログイン画面のバグ" in prompt
        assert "パスワード入力時" in prompt
        assert "bug" in prompt
        assert "urgent" in prompt
        assert "レビュー観点" in prompt

    def test_issue_user_prompt_with_related_mrs(self):
        issue = IssueInfo(
            project_id=42, issue_iid=5, title="Bug", description="", labels=[], state="opened"
        )
        prompt = self.builder.build_issue_user_prompt(
            issue, related_mr_titles=["!10: Fix login", "!11: Add tests"]
        )
        assert "関連MR" in prompt
        assert "!10: Fix login" in prompt
        assert "!11: Add tests" in prompt

    def test_issue_user_prompt_empty_labels(self):
        issue = IssueInfo(
            project_id=42, issue_iid=5, title="Bug", description="", labels=[], state="opened"
        )
        prompt = self.builder.build_issue_user_prompt(issue)
        assert "(なし)" in prompt
