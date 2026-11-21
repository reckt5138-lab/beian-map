@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=python"
if exist "%~dp0..\python_path.txt" set /p PY=<"%~dp0..\python_path.txt"

echo ============================================================
echo  本地抓一次数据：Excel + 完整 JSON + 脱敏 data.json + 网页
echo  不写飞书，不需要联网部署；账号来自 config\credentials.json
echo ============================================================
echo.
"%PY%" -m app.main crawl %*
if errorlevel 1 goto fail
"%PY%" -m app.main publish
if errorlevel 1 goto fail
echo.
echo 完成。Excel 在 output\excel\，网页是 index.html（用「打开地图.bat」看）
echo.
echo 按任意键关闭窗口…
pause >nul
exit /b 0

:fail
echo.
echo 失败。日志在 output\logs\ ，排查方法见 docs\08_故障排查.md
pause >nul
exit /b 1
