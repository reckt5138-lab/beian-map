@echo off
REM Long-running scheduler: starts app\scheduler.py in its own minimized window.
REM Each export runs in a child process that exits when done; the scheduler keeps waiting.
REM Stop it by closing that minimized window, or run: taskkill /F /IM python.exe (careful!)
REM ASCII only: cmd reads .bat in GBK, Chinese comments here would break it.
setlocal
cd /d "%~dp0"

set "PY_EXE=python"
if exist "%~dp0python_path.txt" set /p PY_EXE=<"%~dp0python_path.txt"
if not exist "%PY_EXE%" if exist "E:\Python313\python.exe" set "PY_EXE=E:\Python313\python.exe"
if not exist "%PY_EXE%" if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY_EXE%" if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"

echo.
echo [LEGACY] This local scheduler belongs to the old Feishu route.
echo          v2 already runs daily in GitHub Actions (no PC needed).
echo          Press Ctrl+C now if you did not mean to start a local job.
echo.
timeout /t 5 >nul

start "QingLuan daily export" /min "%PY_EXE%" "%~dp0app\scheduler.py" %*
echo.
echo Scheduler started in a minimized window (taskbar). Keep it open.
echo Daily time and interval are in config\config.json -^> schedule.
echo Log: %~dp0output\logs\scheduler_YYYYMMDD.log
endlocal
