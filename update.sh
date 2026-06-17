#!/bin/bash
# ============================================================
# update.sh — Pull latest changes from GitHub
# Repo: https://github.com/arvineece/CatalogPRO2.git
# Safe: never overwrites config file(s)
# Usage: bash update.sh
# ============================================================

set -e  # Exit immediately on error

# ── CONFIG ──────────────────────────────────────────────────
# Files/dirs to protect (relative to repo root). Add more as needed.
PROTECTED_FILES=(
    "config.py"
    "config.json"
    ".env"
    "catalogpro.db"
)
# ────────────────────────────────────────────────────────────

REPO_URL="https://github.com/arvineece/CatalogPRO2.git"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"   # script lives in the repo root

echo "======================================================"
echo " CatalogPRO2 — Update Script"
echo " $(date)"
echo "======================================================"

cd "$REPO_DIR"

# Make sure this is actually a git repo
if [ ! -d ".git" ]; then
    echo "[ERROR] No .git folder found in $REPO_DIR"
    echo "        Run this script from inside the cloned repo, or clone first:"
    echo "        git clone $REPO_URL"
    exit 1
fi

# ── 1. Save protected files and reset them ──────────────────
echo ""
echo "[1/4] Protecting config files..."
declare -A SAVED_CONFIGS

for FILE in "${PROTECTED_FILES[@]}"; do
    if [ -f "$FILE" ]; then
        SAVED_CONFIGS["$FILE"]=$(cat "$FILE")
        echo "      ✓ Saved: $FILE"
        # Remove local changes so git pull can proceed
        if git ls-files --error-unmatch "$FILE" >/dev/null 2>&1; then
            git checkout HEAD -- "$FILE"
            echo "        ↳ Reset to committed version"
        fi
    else
        echo "      – Not found (skip): $FILE"
    fi
done

# ── 2. Fetch & pull latest from GitHub ──────────────────────
echo ""
echo "[2/4] Pulling latest changes from GitHub..."
git fetch origin
git pull origin "$(git rev-parse --abbrev-ref HEAD)"
echo "      ✓ Pull complete."

# ── 3. Restore protected files ───────────────────────────────
echo ""
echo "[3/4] Restoring config files..."
for FILE in "${!SAVED_CONFIGS[@]}"; do
    echo "${SAVED_CONFIGS[$FILE]}" > "$FILE"
    echo "      ✓ Restored: $FILE"
done

# ── 4. Optional: reload PythonAnywhere web app ───────────────
# Uncomment the lines below and set your correct domain/API token
# if you want to auto-reload your web app after updating.
#
# echo ""
# echo "[4/4] Reloading web app..."
# PA_USERNAME="your_username"
# PA_API_TOKEN="your_api_token"
# PA_DOMAIN="your_username.pythonanywhere.com"
# curl -s -X POST \
#      -H "Authorization: Token $PA_API_TOKEN" \
#      "https://www.pythonanywhere.com/api/v0/user/$PA_USERNAME/webapps/$PA_DOMAIN/reload/" \
#      && echo "      ✓ Web app reloaded."

echo ""
echo "[4/4] Done! ✅"
echo "======================================================"
