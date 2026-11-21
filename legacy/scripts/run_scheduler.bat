@echo off
REM Run the long-lived scheduler without a window (used by the logon task).
REM ASCII only: cmd reads .bat in GBK, Chinese comments here would break it.
setlocal
cd /d "%~dp0.."

set "PY_EXE=python"
if exist "%~dp0..\python_path.txt" set /p PY_EXE=<"%~dp0..\python_path.txt"
if not exist "%PY_EXE%" if exist "E:\Python313\python.exe" set "PY_EXE=E:\Python313\python.exe"
if not exist "%PY_EXE%" if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY_EXE%" if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"

"%PY_EXE%" "%~dp0..\app\scheduler.py" %*
endlocal
