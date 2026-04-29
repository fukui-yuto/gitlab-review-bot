"""
Setup script for test GitLab instance.
Waits for GitLab to be ready, creates a test project, MR, and webhook.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request


GITLAB_URL = os.environ.get("GITLAB_URL", "http://gitlab:8929")
ROOT_PASSWORD = os.environ.get("GITLAB_ROOT_PASSWORD", "reviewbot-test-2024")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://review-bot:8080/api/v1/webhook/gitlab")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "test-webhook-secret-12345")

MAX_WAIT = 600  # seconds
POLL_INTERVAL = 10


def api_request(
    path: str,
    method: str = "GET",
    data: dict | None = None,
    token: str | None = None,
) -> dict:
    url = f"{GITLAB_URL}/api/v4{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["PRIVATE-TOKEN"] = token

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def wait_for_gitlab() -> None:
    print(f"Waiting for GitLab at {GITLAB_URL} ...")
    start = time.time()
    while time.time() - start < MAX_WAIT:
        try:
            req = urllib.request.Request(f"{GITLAB_URL}/-/readiness")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print("GitLab is ready!")
                    return
        except Exception:
            pass
        print(f"  ... waiting ({int(time.time() - start)}s)")
        time.sleep(POLL_INTERVAL)
    print("ERROR: GitLab did not become ready in time", file=sys.stderr)
    sys.exit(1)


def get_root_token() -> str:
    """Create a personal access token for root user."""
    # Use the session API to login and create a token
    try:
        result = api_request(
            "/session",
            method="POST",
            data={"login": "root", "password": ROOT_PASSWORD},
        )
        return result["private_token"]
    except urllib.error.HTTPError:
        # Session API might be disabled; try using the personal access token endpoint
        # Create token via Rails console approach using API
        pass

    # Fallback: try to create via oauth
    print("Attempting to create token via personal access tokens API...")
    # This requires an existing token, so we use a workaround
    # In test environments, we can use the root password to create one
    data = {
        "grant_type": "password",
        "username": "root",
        "password": ROOT_PASSWORD,
    }
    url = f"{GITLAB_URL}/oauth/token"
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    return result["access_token"]


def setup_project(token: str) -> int:
    """Create a test project and return its ID."""
    print("Creating test project...")
    try:
        project = api_request(
            "/projects",
            method="POST",
            data={
                "name": "review-bot-test",
                "description": "Test project for review-bot",
                "initialize_with_readme": True,
                "visibility": "internal",
            },
            token=token,
        )
        project_id = project["id"]
        print(f"Project created: id={project_id}")
        return project_id
    except urllib.error.HTTPError as e:
        if e.code == 400:
            # Project might already exist
            projects = api_request("/projects?search=review-bot-test", token=token)
            for p in projects:
                if p["name"] == "review-bot-test":
                    print(f"Project already exists: id={p['id']}")
                    return p["id"]
        raise


def create_test_branch_and_mr(token: str, project_id: int) -> int:
    """Create a test branch with a file change and open an MR."""
    print("Creating test branch and MR...")

    # Create a file on a new branch
    try:
        api_request(
            f"/projects/{project_id}/repository/files/test_file.py",
            method="POST",
            data={
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
                "commit_message": "Add test file for review",
            },
            token=token,
        )
    except urllib.error.HTTPError as e:
        if e.code != 400:  # file might already exist
            raise

    # Create MR
    try:
        mr = api_request(
            f"/projects/{project_id}/merge_requests",
            method="POST",
            data={
                "source_branch": "feature/test-review",
                "target_branch": "main",
                "title": "Test MR for review-bot",
                "description": "This MR adds a test file to verify review-bot functionality.",
            },
            token=token,
        )
        print(f"MR created: iid={mr['iid']}")
        return mr["iid"]
    except urllib.error.HTTPError as e:
        if e.code == 409:
            mrs = api_request(
                f"/projects/{project_id}/merge_requests?state=opened&source_branch=feature/test-review",
                token=token,
            )
            if mrs:
                print(f"MR already exists: iid={mrs[0]['iid']}")
                return mrs[0]["iid"]
        raise


def setup_webhook(token: str, project_id: int) -> None:
    """Add webhook to the project."""
    print("Setting up webhook...")
    try:
        api_request(
            f"/projects/{project_id}/hooks",
            method="POST",
            data={
                "url": WEBHOOK_URL,
                "token": WEBHOOK_SECRET,
                "note_events": True,
                "push_events": False,
                "merge_requests_events": False,
                "enable_ssl_verification": False,
            },
            token=token,
        )
        print("Webhook created.")
    except urllib.error.HTTPError as e:
        print(f"Webhook setup warning: {e}")


def main() -> None:
    wait_for_gitlab()
    # Give GitLab a bit more time after readiness check
    time.sleep(10)

    token = get_root_token()
    project_id = setup_project(token)
    mr_iid = create_test_branch_and_mr(token, project_id)
    setup_webhook(token, project_id)

    print("\n=== Test GitLab Setup Complete ===")
    print(f"  GitLab URL:  {GITLAB_URL}")
    print(f"  Project ID:  {project_id}")
    print(f"  MR IID:      {mr_iid}")
    print(f"  Webhook URL: {WEBHOOK_URL}")
    print(f'  Root login:  root / {ROOT_PASSWORD}')
    print("\nTo test: go to the MR and comment '/review'")


if __name__ == "__main__":
    main()
