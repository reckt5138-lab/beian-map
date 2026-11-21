@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=python"
if exist "%~dp0..\python_path.txt" set /p PY=<"%~dp0..\python_path.txt"

echo ============================================================
echo  本地打开地图：只监听 127.0.0.1，自动选空闲端口并打开浏览器
echo ============================================================
echo.
"%PY%" "%~dp0local_server.py" %*
