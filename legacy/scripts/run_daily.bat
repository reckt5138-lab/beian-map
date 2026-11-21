@echo off
REM ASCII only on purpose: cmd reads .bat in the OEM codepage (936/GBK),
REM Chinese comments here would be garbled and break the script.
setlocal
cd /d "%~dp0.."

REM Optional: put the full path of python.exe into python_path.txt (project root)
set "PY_EXE=python"
if exist "%~dp0..\python_path.txt" set /p PY_EXE=<"%~dp0..\python_path.txt"

if not exist "%PY_EXE%" if exist "E:\Python313\python.exe" set "PY_EXE=E:\Python313\python.exe"
if not exist "%PY_EXE%" if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY_EXE%" if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"

"%PY_EXE%" "%~dp0..\app\crawler.py" %*
set RC=%ERRORLEVEL%

if not "%RC%"=="0" echo [%date% %time%] export failed, rc=%RC%>> "%~dp0..\run_error.log"

endlocal
exit /b %RC%
