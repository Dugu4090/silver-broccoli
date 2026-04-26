@echo off
REM push.bat \u2014 Windows version of push.sh
REM Usage: push.bat <repo-url> [branch]

setlocal

set "REPO_URL=%~1"
set "BRANCH=%~2"
if "%BRANCH%"=="" set "BRANCH=main"

if "%REPO_URL%"=="" (
  echo Usage: %~nx0 ^<repo-url^> [branch]
  echo Example: %~nx0 https://github.com/me/studymate.git main
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] git is not installed. Get it at https://git-scm.com/downloads
  exit /b 1
)

echo Repo:   %REPO_URL%
echo Branch: %BRANCH%
echo.

if not exist ".git" (
  echo Initializing new git repo...
  git init -q
)

if not exist ".gitignore" (
  > .gitignore (
    echo .env
    echo .env.local
    echo __pycache__/
    echo *.pyc
    echo .venv/
    echo venv/
    echo *.db
    echo *.sqlite
    echo .cache/
    echo .aye/
    echo node_modules/
    echo .next/
    echo .vercel/
    echo .vscode/
    echo .idea/
    echo .DS_Store
    echo *.log
  )
)

git config user.email >nul 2>&1
if errorlevel 1 (
  git config user.email "you@example.com"
  git config user.name  "Your Name"
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin "%REPO_URL%"
) else (
  git remote set-url origin "%REPO_URL%"
)

git checkout -B "%BRANCH%" >nul 2>&1
git add -A

for /f "tokens=2 delims=/" %%a in ('git diff --cached --name-only ^| findstr /R /C:"^\.env$"') do (
  echo [ERROR] .env is staged. Add it to .gitignore and run: git rm --cached .env
  exit /b 1
)

for /f %%a in ('git diff --cached --name-only') do set "HAS_CHANGES=1"
if defined HAS_CHANGES (
  for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set "NOW=%%i"
  git commit -m "Update: %NOW% UTC" -q
  echo Committed.
) else (
  echo Nothing new to commit \u2014 will still force-push current HEAD.
)

echo Force pushing to %BRANCH%...
git push -u origin "%BRANCH%" --force

echo.
echo Done!
endlocal
