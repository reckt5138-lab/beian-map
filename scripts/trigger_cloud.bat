@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=python"
if exist "%~dp0..\python_path.txt" set /p PY=<"%~dp0..\python_path.txt"

echo ============================================================
echo  手动刷新数据：触发云端每天 02:10 的任务，不改代码
echo ============================================================
echo.
"%PY%" "%~dp0refresh.py" %*
echo.
echo 按任意键关闭窗口…
pause >nul
