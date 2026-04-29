#!/bin/bash
# Full automated test suite runner
# Usage: bash scripts/run_tests.sh [--ci]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

CI_MODE="${1:-}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "  GitLab Review Bot - Test Suite"
echo "========================================="

# 1. Install dependencies
echo -e "\n${YELLOW}[1/5] Installing dependencies...${NC}"
if command -v uv &>/dev/null; then
    uv pip install --system -e ".[dev]" --quiet 2>/dev/null || uv pip install -e ".[dev]" --quiet
else
    pip install -e ".[dev]" --quiet
fi
echo -e "${GREEN}  Dependencies installed.${NC}"

# 2. Lint check
echo -e "\n${YELLOW}[2/5] Running ruff lint...${NC}"
if ruff check src/ tests/; then
    echo -e "${GREEN}  Lint passed.${NC}"
else
    echo -e "${RED}  Lint failed!${NC}"
    [ "$CI_MODE" = "--ci" ] && exit 1
fi

# 3. Format check
echo -e "\n${YELLOW}[3/5] Running ruff format check...${NC}"
if ruff format --check src/ tests/; then
    echo -e "${GREEN}  Format check passed.${NC}"
else
    echo -e "${YELLOW}  Format issues found. Run 'ruff format src/ tests/' to fix.${NC}"
    [ "$CI_MODE" = "--ci" ] && exit 1
fi

# 4. Type check
echo -e "\n${YELLOW}[4/5] Running mypy type check...${NC}"
if mypy src/review_bot/ --ignore-missing-imports; then
    echo -e "${GREEN}  Type check passed.${NC}"
else
    echo -e "${YELLOW}  Type check warnings found.${NC}"
fi

# 5. Unit + Integration tests with coverage
echo -e "\n${YELLOW}[5/5] Running pytest with coverage...${NC}"
pytest tests/ \
    --cov=review_bot \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    -v \
    --tb=short

echo -e "\n${GREEN}=========================================${NC}"
echo -e "${GREEN}  All checks completed!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo "Coverage report: htmlcov/index.html"
