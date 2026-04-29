"""
E2E test: Post /review comment via GitLab API and verify bot responds.

Usage:
    python scripts/e2e_review_test.py [--gitlab-url URL] [--password PASSWORD]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def api(
    gitlab_url: str,
    method: str,
    path: str,
    data: dict | None = None,
    token: str | None = None,
) -> dict | list:
    url = f"{gitlab_url}/api/v4{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_token(gitlab_url: str, password: str) -> str:
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


def find_project(gitlab_url: str, token: str) -> int:
    projects = api(gitlab_url, "GET", "/projects?search=review-bot-test", token=token)
    for p in projects:
        if p["name"] == "review-bot-test":
            return p["id"]
    print("ERROR: Project 'review-bot-test' not found. Run setup_and_run.py first.")
    sys.exit(1)


def find_mr(gitlab_url: str, token: str, project_id: int) -> int:
    mrs = api(
        gitlab_url,
        "GET",
        f"/projects/{project_id}/merge_requests?state=opened",
        token=token,
    )
    if mrs:
        return mrs[0]["iid"]
    print("ERROR: No open MR found.")
    sys.exit(1)


def find_issue(gitlab_url: str, token: str, project_id: int) -> int:
    issues = api(
        gitlab_url,
        "GET",
        f"/projects/{project_id}/issues?state=opened",
        token=token,
    )
    for i in issues:
        if "Test Issue" in i.get("title", ""):
            return i["iid"]
    print("ERROR: No test Issue found.")
    sys.exit(1)


def ensure_procedure_issue(gitlab_url: str, token: str, project_id: int) -> int:
    """Create a '手順書' Issue for review testing."""
    issues = api(gitlab_url, "GET", f"/projects/{project_id}/issues?state=opened", token=token)
    for i in issues:
        if "デプロイ手順書" in i.get("title", ""):
            return i["iid"]

    issue = api(
        gitlab_url,
        "POST",
        f"/projects/{project_id}/issues",
        {
            "title": "デプロイ手順書レビュー依頼",
            "description": (
                "## デプロイ手順書\n\n"
                "### 1. 事前準備\n"
                "- サーバーにSSHでログイン\n"
                "- 現在のバージョンを確認: `cat /app/VERSION`\n\n"
                "### 2. デプロイ手順\n"
                "1. リポジトリの最新を取得: `git pull origin main`\n"
                "2. Docker イメージをビルド: `docker compose build`\n"
                "3. サービスを再起動: `docker compose up -d`\n"
                "4. ヘルスチェック: `curl http://localhost:8080/health`\n\n"
                "### 3. ロールバック手順\n"
                "- 前バージョンに戻す場合:\n"
                "  ```bash\n"
                "  git checkout <previous-tag>\n"
                "  docker compose up -d --build\n"
                "  ```\n\n"
                "### 4. 確認事項\n"
                "- [ ] ヘルスチェックが200を返す\n"
                "- [ ] ログにエラーがない\n"
            ),
            "labels": "documentation,review-needed",
        },
        token,
    )
    return issue["iid"]


def get_notes(gitlab_url: str, token: str, project_id: int, noteable_type: str, iid: int) -> list:
    if noteable_type == "mr":
        path = f"/projects/{project_id}/merge_requests/{iid}/notes"
    else:
        path = f"/projects/{project_id}/issues/{iid}/notes"
    return api(gitlab_url, "GET", path, token=token)


def post_note(
    gitlab_url: str, token: str, project_id: int, noteable_type: str, iid: int, body: str
) -> dict:
    if noteable_type == "mr":
        path = f"/projects/{project_id}/merge_requests/{iid}/notes"
    else:
        path = f"/projects/{project_id}/issues/{iid}/notes"
    return api(gitlab_url, "POST", path, {"body": body}, token=token)


def wait_for_bot_response(
    gitlab_url: str,
    token: str,
    project_id: int,
    noteable_type: str,
    iid: int,
    after_note_id: int,
    timeout: int = 30,
) -> str | None:
    """Wait for a bot comment (containing 'review-bot') after a given note ID."""
    start = time.time()
    while time.time() - start < timeout:
        notes = get_notes(gitlab_url, token, project_id, noteable_type, iid)
        for note in notes:
            if note["id"] > after_note_id and "review-bot" in note.get("body", ""):
                return note["body"]
        time.sleep(2)
    return None


def check(name: str, ok: bool, results: list) -> None:
    status = "PASS" if ok else "FAIL"
    color = "\033[0;32m" if ok else "\033[0;31m"
    nc = "\033[0m"
    print(f"  {color}{status}: {name}{nc}")
    results.append(ok)


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E review-bot test")
    parser.add_argument("--gitlab-url", default="http://localhost:8929")
    parser.add_argument("--password", default="reviewbot-test-2024")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    results: list[bool] = []

    print("=========================================")
    print("  E2E Review Bot Test")
    print("=========================================\n")

    # Check bot is running
    print("[0] Checking review-bot health...")
    try:
        req = urllib.request.Request("http://localhost:8080/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read().decode())
        check("review-bot is running", health.get("status") == "ok", results)
    except Exception as e:
        check(f"review-bot is running ({e})", False, results)
        print("\n  ERROR: review-bot is not running on port 8080.")
        print("  Start it first: python scripts/start_bot.py")
        sys.exit(1)

    token = get_token(args.gitlab_url, args.password)
    project_id = find_project(args.gitlab_url, token)
    mr_iid = find_mr(args.gitlab_url, token, project_id)
    issue_iid = find_issue(args.gitlab_url, token, project_id)

    # Test 1: MR /review
    print(f"\n[1] Testing /review on MR !{mr_iid}...")
    note = post_note(args.gitlab_url, token, project_id, "mr", mr_iid, "/review")
    print(f"  Posted /review (note_id={note['id']})")
    body = wait_for_bot_response(
        args.gitlab_url, token, project_id, "mr", mr_iid, note["id"], args.timeout
    )
    check("MR /review: bot responded", body is not None, results)
    if body:
        check("MR /review: contains review content", "レビュー" in body or "review" in body.lower(), results)

    # Test 2: MR /review help
    print(f"\n[2] Testing /review help on MR !{mr_iid}...")
    note = post_note(args.gitlab_url, token, project_id, "mr", mr_iid, "/review help")
    print(f"  Posted /review help (note_id={note['id']})")
    body = wait_for_bot_response(
        args.gitlab_url, token, project_id, "mr", mr_iid, note["id"], args.timeout
    )
    check("MR /review help: bot responded", body is not None, results)
    if body:
        check("MR /review help: contains template list", "/review general" in body, results)

    # Test 3: MR /review security
    print(f"\n[3] Testing /review security on MR !{mr_iid}...")
    note = post_note(args.gitlab_url, token, project_id, "mr", mr_iid, "/review security")
    print(f"  Posted /review security (note_id={note['id']})")
    body = wait_for_bot_response(
        args.gitlab_url, token, project_id, "mr", mr_iid, note["id"], args.timeout
    )
    check("MR /review security: bot responded", body is not None, results)

    # Test 4: Issue /review
    print(f"\n[4] Testing /review on Issue #{issue_iid}...")
    note = post_note(args.gitlab_url, token, project_id, "issue", issue_iid, "/review")
    print(f"  Posted /review (note_id={note['id']})")
    body = wait_for_bot_response(
        args.gitlab_url, token, project_id, "issue", issue_iid, note["id"], args.timeout
    )
    check("Issue /review: bot responded", body is not None, results)
    if body:
        check("Issue /review: contains Issue review", "Issue" in body or "レビュー" in body, results)

    # Test 5: Create a "手順書" Issue and review it
    print("\n[5] Testing /review on 手順書 Issue...")
    procedure_issue = ensure_procedure_issue(args.gitlab_url, token, project_id)
    note = post_note(
        args.gitlab_url, token, project_id, "issue", procedure_issue, "/review"
    )
    print(f"  Posted /review on 手順書 Issue #{procedure_issue} (note_id={note['id']})")
    body = wait_for_bot_response(
        args.gitlab_url, token, project_id, "issue", procedure_issue, note["id"], args.timeout
    )
    check("手順書 Issue /review: bot responded", body is not None, results)
    if body:
        check(
            "手順書 Issue /review: contains review",
            "review-bot" in body.lower() or "レビュー" in body,
            results,
        )

    # Summary
    passed = sum(results)
    total = len(results)
    print(f"\n=========================================")
    print(f"  E2E Results: {passed}/{total} passed")
    if passed == total:
        print(f"  \033[0;32mAll passed!\033[0m")
    else:
        print(f"  \033[0;31m{total - passed} failed\033[0m")
    print(f"=========================================")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
