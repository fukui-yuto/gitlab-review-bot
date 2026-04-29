"""Inline integration tests that verify core components work together."""

import sys

sys.path.insert(0, "src")


def main() -> bool:
    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            print(f"  PASS: {name}")
            passed += 1
        else:
            print(f"  FAIL: {name}")
            failed += 1

    # Test 1: Token verification
    from review_bot.core.security import verify_gitlab_signature

    check("Valid token accepted", verify_gitlab_signature("secret", "secret"))
    check("Invalid token rejected", not verify_gitlab_signature("wrong", "secret"))
    check("Empty token rejected", not verify_gitlab_signature("", "secret"))

    # Test 2: Command parsing
    from review_bot.domain.command import parse_review_command

    cmd = parse_review_command("/review")
    check("Default review command", cmd is not None and cmd.template == "general")

    cmd = parse_review_command("/review security")
    check("Template review command", cmd is not None and cmd.template == "security")

    cmd = parse_review_command("/review help")
    check("Help command", cmd is not None and cmd.template == "help")

    check("Non-command ignored", parse_review_command("hello world") is None)

    # Test 3: Settings loading
    from review_bot.core.config import load_settings

    settings = load_settings("config/settings.example.yaml")
    check("Settings port", settings.app.port == 8080)
    check("Settings provider", settings.llm.provider == "gemini")

    # Test 4: Template loading
    from review_bot.services.template_loader import TemplateLoader

    loader = TemplateLoader("config/templates")
    check("4 templates loaded", len(loader.available_names()) == 4)
    check("general exists", loader.get("general") is not None)
    check("security exists", loader.get("security") is not None)
    check("code_quality exists", loader.get("code_quality") is not None)
    check("test exists", loader.get("test") is not None)
    check("nonexistent is None", loader.get("nonexistent") is None)
    help_text = loader.format_help()
    check("help contains /review general", "/review general" in help_text)

    # Test 5: Prompt builder (MR)
    from review_bot.domain.models import FileDiff, IssueInfo
    from review_bot.services.prompt_builder import PromptBuilder

    builder = PromptBuilder()
    template = loader.get("general")
    prompt = builder.build_user_prompt(
        template,
        mr_title="Test MR",
        mr_description="Test desc",
        target_branch="main",
        diffs=[FileDiff(old_path="a.py", new_path="a.py", diff="+x=1")],
    )
    check("MR prompt has title", "Test MR" in prompt)
    check("MR prompt has file", "a.py" in prompt)

    # Test 6: Prompt builder (Issue)
    issue = IssueInfo(42, 5, "Bug Title", "Bug description", ["bug", "urgent"], "opened")
    issue_prompt = builder.build_issue_user_prompt(issue)
    check("Issue prompt has title", "Bug Title" in issue_prompt)
    check("Issue prompt has label", "bug" in issue_prompt)
    check("Issue prompt has review points", "レビュー観点" in issue_prompt)

    issue_prompt_with_mrs = builder.build_issue_user_prompt(
        issue, related_mr_titles=["!10: Fix login"]
    )
    check("Issue prompt has related MR", "!10: Fix login" in issue_prompt_with_mrs)

    # Summary
    total = passed + failed
    print(f"\n  Results: {passed}/{total} passed")
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
