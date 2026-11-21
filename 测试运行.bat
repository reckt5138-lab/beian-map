@echo off
REM Local test run: crawl -> Excel + data.json + local page. Feishu is NOT used.
REM ASCII only: cmd reads .bat in the OEM codepage, Chinese comments here would break it.
setlocal
cd /d "%~dp0"

set "PY_EXE=python"
if exist "%~dp0python_path.txt" set /p PY_EXE=<"%~dp0python_path.txt"

echo [1/3] crawling (no Feishu) ...
"%PY_EXE%" "%~dp0app\crawler.py" --no-feishu --json-out "%~dp0data.json" %*
if errorlevel 1 goto fail

echo [2/3] building local page ...
"%PY_EXE%" "%~dp0app\build_map_html.py" --from-json "%~dp0data.json" --out "%~dp0index.html"
if errorlevel 1 goto fail

echo [3/3] done
set "LATEST="
for %%f in ("%~dp0output\*.xlsx") do set "LATEST=%%~f"
if defined LATEST (
  echo Excel : %LATEST%
  start "" "%LATEST%"
) else (
  echo Excel : not found in output\
)
echo Data  : %~dp0data.json
echo Page  : %~dp0index.html  (double-click to open)
echo.
pause
exit /b 0

:fail
echo.
echo Run failed. Check output\logs\crawl_YYYYMMDD.log for details.
pause
exit /b 1
