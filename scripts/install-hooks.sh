#!/usr/bin/env bash
# ADR Ledger — Git hooks installer (Linux portable, no Nix required)
# Equivalent of the `adr-install-hooks` Nix derivation in flake.nix
# Usage: bash scripts/install-hooks.sh
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing ADR git hooks..."

# --- pre-commit: ADR schema + chain integrity + SBOM drift ---
cat > "$HOOKS_DIR/pre-commit" << 'HOOK'
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
CHAIN_DIR="$REPO_ROOT/.chain"
PYTHON="python3.13"
ERRORS=0

# 1. ADR Schema Validation
MODIFIED_ADRS=$(git diff --cached --name-only --diff-filter=ACM | grep -E 'adr/.*\.md$' || true)

if [ -n "$MODIFIED_ADRS" ]; then
  echo "Validating ADR schemas..."
  for adr in $MODIFIED_ADRS; do
    $PYTHON - "$adr" << 'PYEOF'
import re, sys, yaml

adr = sys.argv[1]
with open(adr) as f:
    content = f.read()

match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if not match:
    print(f'No YAML frontmatter: {adr}', file=sys.stderr)
    sys.exit(1)
try:
    data = yaml.safe_load(match.group(1))
    for field in ['id', 'title', 'status', 'date']:
        if field not in data:
            print(f'Missing field: {field} in {adr}', file=sys.stderr)
            sys.exit(1)
except Exception as e:
    print(f'Invalid YAML in {adr}: {e}', file=sys.stderr)
    sys.exit(1)
PYEOF
    [ $? -eq 0 ] || ERRORS=$((ERRORS + 1))
  done
  [ $ERRORS -eq 0 ] && echo "  ADR schemas valid"
fi

# 2. Chain Integrity
CHAIN_MODIFIED=$(git diff --cached --name-only | grep -E '\.chain/' || true)

if [ -n "$CHAIN_MODIFIED" ] && [ -f "$CHAIN_DIR/chain.json" ]; then
  echo "Verifying chain integrity..."
  cd "$REPO_ROOT"
  if ! $PYTHON .chain/chain_manager.py verify > /dev/null 2>&1; then
    echo "  Chain integrity check FAILED" >&2
    ERRORS=$((ERRORS + 1))
  else
    echo "  Chain integrity OK"
  fi
fi

# 3. SBOM Drift Detection
DEPS_MODIFIED=$(git diff --cached --name-only | grep -E '(flake\.nix|flake\.lock)' || true)

if [ -n "$DEPS_MODIFIED" ] && [ -f "$CHAIN_DIR/sbom/sbom_current.json" ]; then
  echo "Checking SBOM drift..."
  cd "$REPO_ROOT"
  DRIFT=$($PYTHON .chain/sbom_manager.py verify 2>&1) || true
  if echo "$DRIFT" | grep -q "DRIFT DETECTED"; then
    echo "  SBOM drift detected — run 'adr sbom generate' to update" >&2
    echo "  $DRIFT" >&2
  else
    echo "  SBOM in sync"
  fi
fi

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "Pre-commit failed with $ERRORS error(s)" >&2
  exit 1
fi
HOOK

chmod +x "$HOOKS_DIR/pre-commit"

# --- post-merge: regenerar knowledge base após merge ---
cat > "$HOOKS_DIR/post-merge" << HOOK
#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=\$(git rev-parse --show-toplevel)
echo "Regenerating knowledge artifacts..."
bash "\$REPO_ROOT/scripts/adr" sync
echo "Knowledge synchronized after merge"
HOOK

chmod +x "$HOOKS_DIR/post-merge"

# --- post-commit: regenerar knowledge base após commit ---
cat > "$HOOKS_DIR/post-commit" << HOOK
#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=\$(git rev-parse --show-toplevel)
echo "Regenerating knowledge artifacts..."
bash "\$REPO_ROOT/scripts/adr" sync
echo "Knowledge synchronized after commit"
HOOK

chmod +x "$HOOKS_DIR/post-commit"

echo "Git hooks installed:"
echo "  pre-commit  — ADR schema validation + chain integrity + SBOM drift"
echo "  post-merge  — Auto-sync knowledge base after merge"
echo "  post-commit — Auto-sync knowledge base after commit"
