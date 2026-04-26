#!/usr/bin/env bash
# push.sh \u2014 force-push the current project to a GitHub repo.
#
# Usage:
#   ./push.sh <repo-url> [branch]
#
# Examples:
#   ./push.sh https://github.com/me/studymate.git
#   ./push.sh git@github.com:me/studymate.git main
#   ./push.sh https://<TOKEN>@github.com/me/studymate.git main

set -euo pipefail

REPO_URL="${1:-}"
BRANCH="${2:-main}"

if [[ -z "$REPO_URL" ]]; then
  echo "Usage: $0 <repo-url> [branch]"
  echo "Example: $0 https://github.com/me/studymate.git main"
  exit 1
 fi

if ! command -v git >/dev/null 2>&1; then
  echo "\u274c git is not installed. Install it first: https://git-scm.com/downloads"
  exit 1
fi

echo "\ud83d\udce6 Repo:   $REPO_URL"
echo "\ud83c\udf3f Branch: $BRANCH"
echo

# 1. Init repo if needed
if [[ ! -d .git ]]; then
  echo "\ud83d\udd27 Initializing new git repo..."
  git init -q
fi

# 2. Ensure .gitignore exists with safe defaults
if [[ ! -f .gitignore ]]; then
  echo "\u270d\ufe0f  Creating .gitignore..."
  cat > .gitignore <<'EOF'
# Secrets
.env
.env.local
.env.*.local

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/
env/
*.egg-info/
.pytest_cache/
.mypy_cache/

# Databases & caches
*.db
*.sqlite
*.sqlite3
.cache/
.aye/
.nicegui/

# Node / Next.js
node_modules/
.next/
out/
.vercel/

# IDE / OS
.vscode/
.idea/
.DS_Store
Thumbs.db

# Logs
*.log
EOF
fi

# 3. Configure user identity if missing (uses defaults to avoid commit failure)
if ! git config user.email >/dev/null; then
  echo "\u2139\ufe0f  Setting local git user (override anytime with `git config user.email`)"
  git config user.email "${GIT_EMAIL:-you@example.com}"
  git config user.name  "${GIT_NAME:-Your Name}"
fi

# 4. Set / update origin remote
if git remote get-url origin >/dev/null 2>&1; then
  echo "\ud83d\udd17 Updating existing 'origin' remote..."
  git remote set-url origin "$REPO_URL"
else
  echo "\ud83d\udd17 Adding 'origin' remote..."
  git remote add origin "$REPO_URL"
fi

# 5. Switch to target branch
git checkout -B "$BRANCH" >/dev/null 2>&1

# 6. Stage everything
git add -A

# 7. Safety: refuse to commit a tracked .env
if git diff --cached --name-only | grep -E '(^|/)\.env$' >/dev/null; then
  echo "\u274c Refusing: .env is staged. Add it to .gitignore and run: git rm --cached .env"
  exit 1
fi

# 8. Commit (allow empty so re-runs don't fail)
MSG="Update: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
if git diff --cached --quiet; then
  echo "\u2139\ufe0f  Nothing new to commit \u2014 will still force-push current HEAD."
else
  git commit -m "$MSG" -q
  echo "\u2705 Committed: $MSG"
fi

# 9. Force push
echo "\ud83d\ude80 Force pushing to $BRANCH..."
git push -u origin "$BRANCH" --force

echo
echo "\ud83c\udf89 Done! Your code is live at:"
echo "   ${REPO_URL%.git}"
