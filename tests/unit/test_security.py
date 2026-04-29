from review_bot.core.security import verify_gitlab_signature


class TestVerifyGitlabSignature:
    def test_valid_signature(self):
        assert verify_gitlab_signature("my-secret", "my-secret") is True

    def test_invalid_signature(self):
        assert verify_gitlab_signature("wrong", "my-secret") is False

    def test_empty_received(self):
        assert verify_gitlab_signature("", "my-secret") is False

    def test_empty_expected(self):
        assert verify_gitlab_signature("something", "") is False

    def test_both_empty(self):
        assert verify_gitlab_signature("", "") is False
