"""
Fully automated setup: obtain GitLab token, register webhook, create test data.
Outputs a .env.test file that review-bot can use directly.

Usage:
    python scripts/setup_and_run.py [--gitlab-url URL] [--password PASSWORD]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

WEBHOOK_SECRET = "test-webhook-secret-12345"


def api(
    gitlab_url: str,
    method: str,
    path: str,
    data: dict | None = None,
    token: str | None = None,
) -> dict:
    url = f"{gitlab_url}/api/v4{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_oauth_token(gitlab_url: str, password: str) -> str:
    data = json.dumps(
        {"grant_type": "password", "username": "root", "password": password}
    ).encode()
    req = urllib.request.Request(
        f"{gitlab_url}/oauth/token",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["access_token"]


def create_personal_access_token(gitlab_url: str, oauth_token: str) -> str:
    """Create a persistent personal access token for the root user."""
    try:
        result = api(
            gitlab_url,
            "POST",
            "/users/1/personal_access_tokens",
            data={
                "name": "review-bot-token",
                "scopes": ["api", "read_api", "read_user"],
            },
            token=oauth_token,
        )
        return result["token"]
    except urllib.error.HTTPError:
        # Token might already exist; try using the OAuth token directly
        return oauth_token


def ensure_project(gitlab_url: str, token: str) -> int:
    projects = api(gitlab_url, "GET", "/projects?search=review-bot-test", token=token)
    for p in projects:
        if p["name"] == "review-bot-test":
            print(f"  Project exists: id={p['id']}")
            return p["id"]
    p = api(
        gitlab_url,
        "POST",
        "/projects",
        {"name": "review-bot-test", "initialize_with_readme": True, "visibility": "internal"},
        token,
    )
    print(f"  Created project: id={p['id']}")
    return p["id"]


def ensure_test_branch_and_mr(gitlab_url: str, token: str, project_id: int) -> int:
    # Create file on new branch
    try:
        api(
            gitlab_url,
            "POST",
            f"/projects/{project_id}/repository/files/test_app.py",
            {
                "branch": "feature/test-review",
                "start_branch": "main",
                "content": (
                    "def hello():\n"
                    "    print('hello world')\n"
                    "\n"
                    "def add(a, b):\n"
                    "    return a + b\n"
                    "\n"
                    "# TODO: add error handling\n"
                    "def divide(a, b):\n"
                    "    return a / b\n"
                ),
                "commit_message": "add test file",
            },
            token,
        )
        print("  Created test file on branch")
    except urllib.error.HTTPError:
        print("  Test file already exists")

    # Create MR
    mrs = api(
        gitlab_url,
        "GET",
        f"/projects/{project_id}/merge_requests?state=opened&source_branch=feature/test-review",
        token=token,
    )
    if mrs:
        print(f"  MR exists: iid={mrs[0]['iid']}")
        return mrs[0]["iid"]

    mr = api(
        gitlab_url,
        "POST",
        f"/projects/{project_id}/merge_requests",
        {
            "source_branch": "feature/test-review",
            "target_branch": "main",
            "title": "Test MR for review-bot",
            "description": "This MR adds a test file to verify review-bot functionality.",
        },
        token,
    )
    print(f"  Created MR: iid={mr['iid']}")
    return mr["iid"]


def ensure_issue(gitlab_url: str, token: str, project_id: int) -> int:
    issues = api(gitlab_url, "GET", f"/projects/{project_id}/issues?state=opened", token=token)
    for i in issues:
        if "Test Issue" in i.get("title", ""):
            print(f"  Issue exists: iid={i['iid']}")
            return i["iid"]

    issue = api(
        gitlab_url,
        "POST",
        f"/projects/{project_id}/issues",
        {
            "title": "Test Issue for review-bot",
            "description": (
                "## 概要\nreview-bot の動作確認用Issueです。\n\n"
                "## 受け入れ基準\n- [ ] `/review` コマンドで自動レビューが実行される\n"
                "- [ ] レビュー結果がコメントとして投稿される\n"
            ),
            "labels": "bug,test",
        },
        token,
    )
    print(f"  Created Issue: iid={issue['iid']}")
    return issue["iid"]


def enable_local_requests(gitlab_url: str, token: str) -> None:
    """Allow webhooks to local network (required for localhost testing)."""
    try:
        api(
            gitlab_url,
            "PUT",
            "/application/settings",
            {
                "allow_local_requests_from_web_hooks_and_services": True,
                "allow_local_requests_from_system_hooks": True,
            },
            token,
        )
        print("  Local network requests enabled for webhooks")
    except urllib.error.HTTPError as e:
        print(f"  Warning: could not enable local requests: {e}")


def ensure_webhook(
    gitlab_url: str, token: str, project_id: int, bot_url: str
) -> None:
    webhook_url = f"{bot_url}/api/v1/webhook/gitlab"

    # Check existing webhooks
    hooks = api(gitlab_url, "GET", f"/projects/{project_id}/hooks", token=token)
    for h in hooks:
        if h.get("url") == webhook_url:
            print(f"  Webhook exists: id={h['id']}")
            return

    api(
        gitlab_url,
        "POST",
        f"/projects/{project_id}/hooks",
        {
            "url": webhook_url,
            "token": WEBHOOK_SECRET,
            "note_events": True,
            "push_events": False,
            "merge_requests_events": False,
            "issues_events": False,
            "enable_ssl_verification": False,
        },
        token,
    )
    print(f"  Webhook registered: {webhook_url}")


def write_env_test(
    gitlab_url: str, gitlab_token: str, llm_provider: str, env_path: str = ".env.test"
) -> None:
    content = (
        f"GITLAB_URL={gitlab_url}\n"
        f"GITLAB_TOKEN={gitlab_token}\n"
        f"GITLAB_WEBHOOK_SECRET={WEBHOOK_SECRET}\n"
        f"LLM_PROVIDER={llm_provider}\n"
        f"GEMINI_API_KEY=\n"
        f"OPENAI_API_KEY=\n"
    )
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Wrote {env_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup test environment for review-bot")
    parser.add_argument("--gitlab-url", default="http://localhost:8929")
    parser.add_argument("--password", default="reviewbot-test-2024")
    parser.add_argument("--bot-url", default="http://host.docker.internal:8080")
    parser.add_argument("--llm-provider", default="mock")
    args = parser.parse_args()

    print("=== Setup Test Environment ===\n")

    print("[1] Obtaining GitLab token...")
    oauth_token = get_oauth_token(args.gitlab_url, args.password)
    pat = create_personal_access_token(args.gitlab_url, oauth_token)
    print(f"  Token obtained (len={len(pat)})")

    print("\n[2] Setting up project...")
    project_id = ensure_project(args.gitlab_url, oauth_token)

    print("\n[3] Creating test MR...")
    mr_iid = ensure_test_branch_and_mr(args.gitlab_url, oauth_token, project_id)

    print("\n[4] Creating test Issue...")
    issue_iid = ensure_issue(args.gitlab_url, oauth_token, project_id)

    print("\n[5] Enabling local network requests for webhooks...")
    enable_local_requests(args.gitlab_url, oauth_token)

    print("\n[6] Registering webhook...")
    ensure_webhook(args.gitlab_url, oauth_token, project_id, args.bot_url)

    print("\n[7] Writing .env.test...")
    write_env_test(args.gitlab_url, pat, args.llm_provider)

    print(f"\n=== Setup Complete ===")
    print(f"  GitLab:     {args.gitlab_url}")
    print(f"  Project ID: {project_id}")
    print(f"  MR IID:     {mr_iid}")
    print(f"  Issue IID:  {issue_iid}")
    print(f"  Bot URL:    {args.bot_url}")
    print(f"  Provider:   {args.llm_provider}")
    print(f"\n  Login: root / {args.password}")
    print(f"  MR URL:    {args.gitlab_url}/root/review-bot-test/-/merge_requests/{mr_iid}")
    print(f"  Issue URL: {args.gitlab_url}/root/review-bot-test/-/issues/{issue_iid}")
    print(f"\n  Type '/review' in MR or Issue comments to trigger a review!")


if __name__ == "__main__":
    main()
