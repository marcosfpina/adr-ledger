#!/usr/bin/env bash
# =============================================================================
# Git Hooks Installer
# =============================================================================
# Installs feature detection hooks into .git/hooks/
# =============================================================================

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
HOOKS_SRC="${REPO_ROOT}/.hooks"
HOOKS_DEST="${REPO_ROOT}/.git/hooks"

echo "Installing Git Hooks..."

# Ensure .git/hooks exists
mkdir -p "$HOOKS_DEST"

# Symlink hooks
for hook in post-commit; do
    src="${HOOKS_SRC}/${hook}"
    dest="${HOOKS_DEST}/${hook}"

    if [[ -f "$src" ]]; then
        echo "  → Installing ${hook}"
        ln -sf "$src" "$dest"
        chmod +x "$dest"
    fi
done

echo "✓ Hooks installed successfully"
echo ""
echo "Installed hooks:"
ls -lh "$HOOKS_DEST" | grep -v total || true
