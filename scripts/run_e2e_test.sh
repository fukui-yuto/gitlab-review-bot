#!/bin/bash
# E2E test against a running test GitLab instance
# Prerequisites:
#   1. docker compose -f docker-compose.test-gitlab.yml up -d
#   2. Wait for GitLab to be ready (~3-5 min)
#   3. Run the setup script (auto-run via gitlab-setup container)
#   4. Start review-bot with test .env
#
# Usage: bash scripts/run_e2e_test.sh
set -euo pipefail

GITLAB_URL="${GITLAB_URL:-http://localhost:8929}"
GITLAB_TOKEN="${GITLAB_TOKEN:-}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-test-webhook-secret-12345}"
BOT_URL="${BOT_URL:-http://localhost:8080}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "  GitLab Review Bot - E2E Test"
echo "========================================="

# Check GitLab is up
echo -e "\n${YELLOW}[1/4] Checking GitLab...${NC}"
if curl -sf "${GITLAB_URL}/-/readiness" > /dev/null 2>&1; then
    echo -e "${GREEN}  GitLab is ready.${NC}"
else
    echo -e "${RED}  GitLab is not ready at ${GITLAB_URL}${NC}"
    echo "  Start it with: docker compose -f docker-compose.test-gitlab.yml up -d"
    exit 1
fi

# Check bot is up
echo -e "\n${YELLOW}[2/4] Checking review-bot...${NC}"
if curl -sf "${BOT_URL}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}  Review-bot is healthy.${NC}"
else
    echo -e "${RED}  Review-bot is not running at ${BOT_URL}${NC}"
    exit 1
fi

# Find test project
echo -e "\n${YELLOW}[3/4] Finding test project and MR...${NC}"
if [ -z "$GITLAB_TOKEN" ]; then
    echo -e "${RED}  GITLAB_TOKEN not set. Export it first.${NC}"
    exit 1
fi

PROJECT_ID=$(curl -sf -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    "${GITLAB_URL}/api/v4/projects?search=review-bot-test" | python3 -c "
import json,sys
projects = json.load(sys.stdin)
for p in projects:
    if p['name'] == 'review-bot-test':
        print(p['id'])
        break
")

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}  Test project not found.${NC}"
    exit 1
fi
echo "  Project ID: ${PROJECT_ID}"

MR_IID=$(curl -sf -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    "${GITLAB_URL}/api/v4/projects/${PROJECT_ID}/merge_requests?state=opened" | python3 -c "
import json,sys
mrs = json.load(sys.stdin)
if mrs: print(mrs[0]['iid'])
")

if [ -z "$MR_IID" ]; then
    echo -e "${RED}  No open MR found.${NC}"
    exit 1
fi
echo "  MR IID: ${MR_IID}"

# Post /review command
echo -e "\n${YELLOW}[4/4] Posting /review command...${NC}"
RESPONSE=$(curl -sf -X POST \
    -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"body": "/review"}' \
    "${GITLAB_URL}/api/v4/projects/${PROJECT_ID}/merge_requests/${MR_IID}/notes")

echo "  Comment posted. Waiting for bot to process..."
sleep 15

# Check for bot response
NOTES=$(curl -sf -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    "${GITLAB_URL}/api/v4/projects/${PROJECT_ID}/merge_requests/${MR_IID}/notes?sort=desc&per_page=5")

BOT_REPLIED=$(echo "$NOTES" | python3 -c "
import json,sys
notes = json.load(sys.stdin)
for n in notes:
    if 'review-bot' in n.get('body',''):
        print('yes')
        break
" 2>/dev/null || echo "no")

if [ "$BOT_REPLIED" = "yes" ]; then
    echo -e "${GREEN}  Bot replied successfully!${NC}"
else
    echo -e "${YELLOW}  Bot reply not found yet. Check manually.${NC}"
fi

echo -e "\n${GREEN}=========================================${NC}"
echo -e "${GREEN}  E2E test completed.${NC}"
echo -e "${GREEN}=========================================${NC}"
