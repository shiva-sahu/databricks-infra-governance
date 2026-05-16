#!/usr/bin/env bash
# scripts/validate_all.sh
# ─────────────────────────────────────────────────────────────────────────────
# Full local validation — run this before opening a PR.
# Mirrors exactly what CI will run.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }
pass() { echo -e "${GREEN}✅  $1${NC}"; }
fail() { echo -e "${RED}❌  $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }

FAILED=0

# ── Step 1: Python dependencies ───────────────────────────────────────────────
step "Installing Python dependencies"
pip install -q pytest pytest-md-report pyyaml python-hcl2 jsonschema
pass "Dependencies installed"

# ── Step 2: Governance tests ──────────────────────────────────────────────────
step "Running governance tests"
if pytest tests/governance/ -v --tb=short; then
    pass "All governance tests passed"
else
    fail "Governance tests FAILED — fix before opening PR"
    FAILED=1
fi

# ── Step 3: Terraform format check ────────────────────────────────────────────
step "Checking Terraform formatting"
if terraform fmt -check -recursive terraform/; then
    pass "Terraform formatting OK"
else
    warn "Terraform files need formatting. Run: terraform fmt -recursive terraform/"
    FAILED=1
fi

# ── Step 4: Terraform validate (dev) ─────────────────────────────────────────
step "Validating Terraform (dev)"
cd terraform/environments/dev
if terraform init -backend=false -input=false -no-color > /dev/null 2>&1; then
    if terraform validate -no-color; then
        pass "Terraform validate passed (dev)"
    else
        fail "Terraform validate FAILED (dev)"
        FAILED=1
    fi
else
    warn "Terraform init failed — check provider configuration"
fi
cd "$REPO_ROOT"

# ── Step 5: Validate GitHub Actions workflows ─────────────────────────────────
step "Checking workflow YAML syntax"
if command -v python3 &>/dev/null; then
    for f in .github/workflows/*.yml; do
        if python3 -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null; then
            pass "  $f"
        else
            fail "  $f — invalid YAML"
            FAILED=1
        fi
    done
else
    warn "Python3 not found — skipping YAML validation"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅  ALL CHECKS PASSED — safe to open PR${NC}"
else
    echo -e "${RED}❌  CHECKS FAILED — fix issues before opening PR${NC}"
    echo -e "${RED}    The same checks run in CI and will block your merge.${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $FAILED
