@echo off
rem One-click deploy: create repo, push, write secrets, rebuild index.html, trigger Actions.
rem Optional: put the python.exe full path into python_path.txt if 'python' is not on PATH.
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXE=python"
if exist "%~dp0python_path.txt" set /p PY_EXE=<"%~dp0python_path.txt"

if "%~1"=="" (
  echo Usage:
  echo   one-click: type owner / repo / token when asked
  echo   or: %~nx0 --owner NAME --repo REPO --token ghp_xxx
  echo.
  echo Optional Cloudflare Pages ^(free public web link^):
  echo   --cf-token CF_TOKEN --cf-account ACCOUNT_ID --cf-project beian-map
  echo.
)

"%PY_EXE%" scripts\deploy_github.py %*
echo.
pause
