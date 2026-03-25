#!/usr/bin/env bash
# ADR Ledger — Standalone YAML validator (Linux portable)
# Portable equivalent of `nix build .#checks.schema-valid` + `adr-cli validate`
# Usage: bash scripts/validate.sh [adr-dir]
#   adr-dir defaults to ./adr (all statuses)
set -euo pipefail

REPO_ROOT="${ADR_LEDGER_ROOT:-$(git rev-parse --show-toplevel)}"
ADR_DIR="${1:-$REPO_ROOT/adr}"
ERRORS=0
CHECKED=0

if ! ls "$ADR_DIR"/*/*.md >/dev/null 2>&1; then
  echo "No ADRs found in $ADR_DIR"
  exit 0
fi

for adr in "$ADR_DIR"/*/*.md; do
  [ -f "$adr" ] || continue
  echo "  Validating $(basename "$adr")..."

  python3.13 - "$adr" << 'PYEOF'
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
            print(f'Missing required field: {field} in {adr}', file=sys.stderr)
            sys.exit(1)
except Exception as e:
    print(f'Invalid YAML in {adr}: {e}', file=sys.stderr)
    sys.exit(1)
PYEOF
  [ $? -eq 0 ] && CHECKED=$((CHECKED + 1)) || ERRORS=$((ERRORS + 1))
done

if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo "Validation failed: $ERRORS error(s) in $((CHECKED + ERRORS)) ADRs" >&2
  exit 1
fi

echo "All $CHECKED ADRs valid"
