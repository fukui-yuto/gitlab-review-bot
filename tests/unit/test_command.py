import pytest

from review_bot.domain.command import parse_review_command


class TestParseReviewCommand:
    def test_simple_review(self):
        cmd = parse_review_command("/review")
        assert cmd is not None
        assert cmd.template == "general"
        assert cmd.extra_args == {}

    def test_review_with_template(self):
        cmd = parse_review_command("/review security")
        assert cmd is not None
        assert cmd.template == "security"

    def test_review_code_quality(self):
        cmd = parse_review_command("/review code_quality")
        assert cmd is not None
        assert cmd.template == "code_quality"

    def test_review_test(self):
        cmd = parse_review_command("/review test")
        assert cmd is not None
        assert cmd.template == "test"

    def test_review_help(self):
        cmd = parse_review_command("/review help")
        assert cmd is not None
        assert cmd.template == "help"

    def test_review_with_extra_args(self):
        cmd = parse_review_command("/review code_quality --files=src/foo.py")
        assert cmd is not None
        assert cmd.template == "code_quality"
        assert cmd.extra_args == {"files": "src/foo.py"}

    def test_review_with_leading_whitespace(self):
        cmd = parse_review_command("  /review security")
        assert cmd is not None
        assert cmd.template == "security"

    def test_review_with_trailing_whitespace(self):
        cmd = parse_review_command("/review general  ")
        assert cmd is not None
        assert cmd.template == "general"

    def test_not_a_command(self):
        assert parse_review_command("just a regular comment") is None

    def test_empty_string(self):
        assert parse_review_command("") is None

    def test_none_input(self):
        assert parse_review_command(None) is None  # type: ignore[arg-type]

    def test_similar_but_not_command(self):
        assert parse_review_command("please /review this") is None

    def test_slash_only(self):
        assert parse_review_command("/") is None

    def test_review_prefix_but_different(self):
        assert parse_review_command("/reviewer") is None

    def test_multiple_extra_args(self):
        cmd = parse_review_command("/review general --files=a.py --verbose=true")
        assert cmd is not None
        assert cmd.extra_args == {"files": "a.py", "verbose": "true"}
