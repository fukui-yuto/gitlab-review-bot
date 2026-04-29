import hmac


def verify_gitlab_signature(received_token: str, expected_secret: str) -> bool:
    if not expected_secret:
        return False
    return hmac.compare_digest(received_token, expected_secret)
