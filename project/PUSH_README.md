# Push to GitHub

Two scripts are provided:
- `push.sh` \u2014 macOS / Linux / WSL
- `push.bat` \u2014 Windows CMD / PowerShell

## One-time setup

### 1. Create the repo on GitHub
Go to https://github.com/new \u2192 create an empty repo (no README, no license).

### 2. Authenticate (pick one)

**Option A \u2014 GitHub CLI (easiest)**
```bash
gh auth login
```

**Option B \u2014 Personal Access Token**
1. Get token at https://github.com/settings/tokens (scope: `repo`).
2. Use this URL form: `https://<TOKEN>@github.com/<user>/<repo>.git`

**Option C \u2014 SSH key**
```bash
ssh-keygen -t ed25519 -C "you@example.com"
cat ~/.ssh/id_ed25519.pub   # paste into https://github.com/settings/keys
```
Then use: `git@github.com:<user>/<repo>.git`

## Push

### macOS / Linux
```bash
chmod +x push.sh
./push.sh https://github.com/<user>/<repo>.git
# optional branch:
./push.sh https://github.com/<user>/<repo>.git main
```

### Windows
```cmd
push.bat https://github.com/<user>/<repo>.git
```

## What it does
1. `git init` (if needed)
2. Writes a safe `.gitignore`
3. Sets/updates `origin` remote
4. Commits all changes with a timestamp
5. **Force pushes** to the chosen branch (default `main`)

## \u26a0\ufe0f Warning
`--force` **overwrites the remote branch history**. Use only if you're sure no one else has commits there you need to keep.

## Custom git identity
Set env vars before running, or run `git config` after:
```bash
GIT_EMAIL="me@example.com" GIT_NAME="Me" ./push.sh <repo-url>
```
