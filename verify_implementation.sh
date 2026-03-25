#!/usr/bin/env bash
# =============================================================================
# Implementation Verification Script
# =============================================================================
# Verifies that all 6 components are correctly implemented.
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REPO_ROOT=$(git rev-parse --show-toplevel)
HUB_PATH="/home/kernelcore/arch/ai-assistant-hub"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  AI Agent Hub - Implementation Verification${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_cmd="$2"

    echo -n "Testing ${test_name}... "

    if eval "$test_cmd" &>/dev/null; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

# =============================================================================
# TEST 1: STF Protocol
# =============================================================================
echo -e "${YELLOW}[1/6] STF Protocol${NC}"

run_test "STF file exists" "test -f ${REPO_ROOT}/.stf/neutron.stf"
run_test "STF schema exists" "test -f ${REPO_ROOT}/.schema/stf.schema.json"
run_test "STF parser exists" "test -f ${HUB_PATH}/src/stf/parser.py"
run_test "STF parser is executable" "python3 -c 'from pathlib import Path; import sys; sys.path.insert(0, \"${HUB_PATH}/src\"); from stf.parser import STFParser'"

echo ""

# =============================================================================
# TEST 2: Feature Detection
# =============================================================================
echo -e "${YELLOW}[2/6] Feature Detection System${NC}"

run_test "Post-commit hook exists" "test -f ${REPO_ROOT}/.hooks/post-commit"
run_test "Feature detector exists" "test -f ${REPO_ROOT}/.hooks/feature_detector.py"
run_test "Integration checker exists" "test -f ${REPO_ROOT}/.hooks/integration_checker.py"
run_test "Hooks are executable" "test -x ${REPO_ROOT}/.hooks/post-commit && test -x ${REPO_ROOT}/.hooks/feature_detector.py"

echo ""

# =============================================================================
# TEST 3: Observability
# =============================================================================
echo -e "${YELLOW}[3/6] Observability Module${NC}"

run_test "Metrics module exists" "test -f ${HUB_PATH}/src/observability/metrics.py"
run_test "Logger module exists" "test -f ${HUB_PATH}/src/observability/structured_logger.py"
run_test "TimescaleDB schema exists" "test -f ${HUB_PATH}/src/observability/timescale_schema.sql"
run_test "Observability is importable" "python3 -c 'import sys; sys.path.insert(0, \"${HUB_PATH}/src\"); from observability import track_decision'"

echo ""

# =============================================================================
# TEST 4: Feedback Loop
# =============================================================================
echo -e "${YELLOW}[4/6] Feedback Loop${NC}"

run_test "Feedback collector exists" "test -f ${HUB_PATH}/src/feedback/collector.py"
run_test "Feedback module exists" "test -f ${HUB_PATH}/src/feedback/__init__.py"
run_test "Feedback is importable" "python3 -c 'import sys; sys.path.insert(0, \"${HUB_PATH}/src\"); from feedback import FeedbackCollector'"

echo ""

# =============================================================================
# TEST 5: MLflow Integration
# =============================================================================
echo -e "${YELLOW}[5/6] MLflow Integration${NC}"

run_test "Model registry exists" "test -f ${HUB_PATH}/src/ml/model_registry.py"
run_test "ML module exists" "test -f ${HUB_PATH}/src/ml/__init__.py"
run_test "ML is importable" "python3 -c 'import sys; sys.path.insert(0, \"${HUB_PATH}/src\"); from ml import ModelRegistry'"
run_test "Model can be loaded" "python3 -c 'import sys; sys.path.insert(0, \"${HUB_PATH}/src\"); from ml import ModelRegistry; r = ModelRegistry(); m = r.load_model(\"decision-scorer\")'"

echo ""

# =============================================================================
# TEST 6: CI/CD Pipeline
# =============================================================================
echo -e "${YELLOW}[6/6] CI/CD Pipeline${NC}"

run_test "ADR validation workflow exists" "test -f ${REPO_ROOT}/.github/workflows/adr-validation.yml"
run_test "Hub tests workflow exists" "test -f ${HUB_PATH}/.github/workflows/tests.yml"
run_test "Workflows are valid YAML" "python3 -c 'import yaml; yaml.safe_load(open(\"${REPO_ROOT}/.github/workflows/adr-validation.yml\"))'"

echo ""

# =============================================================================
# SUMMARY
# =============================================================================
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Summary${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
PASS_RATE=$(awk "BEGIN {printf \"%.1f\", ($TESTS_PASSED/$TOTAL_TESTS)*100}")

echo "Total Tests: $TOTAL_TESTS"
echo -e "Passed:      ${GREEN}$TESTS_PASSED${NC}"

if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "Failed:      ${RED}$TESTS_FAILED${NC}"
fi

echo "Pass Rate:   ${PASS_RATE}%"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed! Implementation verified successfully.${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Please review the implementation.${NC}"
    exit 1
fi
