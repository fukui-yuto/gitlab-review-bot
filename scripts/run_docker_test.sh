#!/bin/bash
# Fully automated Docker-based integration test + E2E test
# Usage: bash scripts/run_docker_test.sh
set -euo pipefail

cd "$(dirname "$0")/.."

GITLAB_URL="http://localhost:8929"
GITLAB_PASSWORD="reviewbot-test-2024"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS_N=0
FAIL_N=0

ok()   { echo -e "${GREEN}  PASS: $1${NC}"; PASS_N=$((PASS_N+1)); }
ng()   { echo -e "${RED}  FAIL: $1${NC}"; FAIL_N=$((FAIL_N+1)); }

echo "========================================="
echo "  Docker Integration Test Suite"
echo "========================================="

# --- 1. Check GitLab ---
echo -e "\n${YELLOW}[1/6] Checking GitLab...${NC}"
if ! docker ps --format '{{.Names}}' | grep -q test-gitlab; then
    echo "  Starting GitLab..."
    docker compose -f docker-compose.test-gitlab.yml up -d gitlab
fi

for i in $(seq 1 60); do
    CODE=$(curl -sf -o /dev/null -w "%{http_code}" "$GITLAB_URL/" 2>/dev/null || echo "000")
    [ "$CODE" = "302" ] || [ "$CODE" = "200" ] && break
    [ "$i" = "60" ] && { ng "GitLab startup timeout"; exit 1; }
    sleep 10
done
ok "GitLab is ready"

# --- 2. Setup: token, project, MR, Issue, webhook ---
echo -e "\n${YELLOW}[2/6] Setting up test data + webhook...${NC}"
if python3 scripts/setup_and_run.py --gitlab-url "$GITLAB_URL" --password "$GITLAB_PASSWORD" --bot-url "http://host.docker.internal:8080" --llm-provider mock; then
    ok "Test data + webhook setup"
else
    ng "Test data + webhook setup"
fi

# --- 3. Component tests ---
echo -e "\n${YELLOW}[3/6] Running component integration tests...${NC}"
if python3 scripts/docker_inline_test.py; then
    ok "Component tests"
else
    ng "Component tests"
fi

# --- 4. Full pytest ---
echo -e "\n${YELLOW}[4/6] Running full pytest suite...${NC}"
if python3 -m pytest tests/ -v --tb=short --cov=review_bot --cov-report=term-missing; then
    ok "Pytest suite"
else
    ng "Pytest suite"
fi

# --- 5. Start review-bot in background ---
echo -e "\n${YELLOW}[5/6] Starting review-bot (mock LLM)...${NC}"

# Kill any existing bot on port 8080
python3 -c "
import subprocess, sys, platform
if platform.system() == 'Windows':
    r = subprocess.run(['netstat','-ano'], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if ':8080' in line and 'LISTENING' in line:
            pid = line.strip().split()[-1]
            subprocess.run(['taskkill','/PID',pid,'/F'], capture_output=True)
            print(f'  Killed PID {pid}')
else:
    r = subprocess.run(['lsof','-i',':8080','-t'], capture_output=True, text=True)
    for pid in r.stdout.strip().split():
        subprocess.run(['kill', pid])
        print(f'  Killed PID {pid}')
" 2>/dev/null || true

# Start bot in background
python3 scripts/start_bot.py &
BOT_PID=$!
echo "  Bot started (PID=$BOT_PID)"

# Wait for bot to be ready
BOT_READY=false
for i in $(seq 1 20); do
    if curl -sf http://localhost:8080/health >/dev/null 2>&1; then
        BOT_READY=true
        break
    fi
    sleep 1
done

if [ "$BOT_READY" = "true" ]; then
    ok "review-bot started"
else
    ng "review-bot startup"
    kill $BOT_PID 2>/dev/null || true
    exit 1
fi

# --- 6. E2E test ---
echo -e "\n${YELLOW}[6/6] Running E2E review test...${NC}"
if python3 scripts/e2e_review_test.py --gitlab-url "$GITLAB_URL" --password "$GITLAB_PASSWORD" --timeout 30; then
    ok "E2E review test"
else
    ng "E2E review test"
fi

# Cleanup: stop bot
echo ""
echo "  Stopping review-bot..."
python3 -c "
import subprocess, platform
if platform.system() == 'Windows':
    r = subprocess.run(['netstat','-ano'], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if ':8080' in line and 'LISTENING' in line:
            pid = line.strip().split()[-1]
            subprocess.run(['taskkill','/PID',pid,'/F'], capture_output=True)
else:
    subprocess.run(['kill', '$BOT_PID'], capture_output=True)
" 2>/dev/null || true
wait $BOT_PID 2>/dev/null || true

# --- Summary ---
echo ""
echo "========================================="
TOTAL=$((PASS_N + FAIL_N))
echo "  Results: $PASS_N/$TOTAL passed"
if [ "$FAIL_N" -gt 0 ]; then
    echo -e "  ${RED}$FAIL_N failed${NC}"
    exit 1
else
    echo -e "  ${GREEN}All passed!${NC}"
fi
echo "========================================="
