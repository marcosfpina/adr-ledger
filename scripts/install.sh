#!/usr/bin/env bash
# ADR Ledger — Linux non-Nix installer
# Usage: bash scripts/install.sh [--skip-deps] [--no-hooks]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKIP_DEPS=false
NO_HOOKS=false

for arg in "$@"; do
  case "$arg" in
    --skip-deps) SKIP_DEPS=true ;;
    --no-hooks)  NO_HOOKS=true ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}OK${NC}  $1"; }
warn() { echo -e "${YELLOW}WARN${NC} $1"; }
err()  { echo -e "${RED}ERR${NC} $1" >&2; exit 1; }

echo "ADR Ledger — Linux installer"
echo "Repo: $REPO_ROOT"
echo ""

# --- 1. Dependency check ---
if [ "$SKIP_DEPS" = false ]; then
  command -v git        >/dev/null 2>&1 || err "'git' not found in PATH"
  command -v bash       >/dev/null 2>&1 || err "'bash' not found in PATH"
  command -v python3.13 >/dev/null 2>&1 || err "'python3.13' not found. Install Python 3.13 first."
  ok "python3.13 found"

  python3.13 -c "import yaml" 2>/dev/null \
    || err "pyyaml not installed. Run: pip install pyyaml"
  ok "pyyaml found"

  python3.13 -c "import nacl" 2>/dev/null \
    || err "pynacl not installed. Run: pip install pynacl"
  ok "pynacl found"
fi

# --- 2. Make CLI executable ---
chmod +x "$REPO_ROOT/scripts/adr"
ok "scripts/adr is executable"

# --- 3. Install git hooks ---
if [ "$NO_HOOKS" = false ]; then
  if [ -d "$REPO_ROOT/.git" ]; then
    bash "$REPO_ROOT/scripts/install-hooks.sh"
  else
    warn "Not a git repo root — skipping hook installation"
  fi
fi

echo ""
echo "Installation complete."
echo ""
echo "Add to PATH (add to ~/.bashrc or ~/.zshrc):"
echo "  export PATH=\"$REPO_ROOT/scripts:\$PATH\""
echo ""
echo "Quick start:"
echo "  adr list"
echo "  adr new -t \"My Decision\" -p CEREBRO -c major"
echo "  adr sync"
