@echo off
rem 本文件必须以 GBK(936) 编码保存：改成 UTF-8 后中文会乱码，甚至导致命令解析失败
rem 布局：首页菜单（1 主菜单 / 9 清空线上仓库 / 0 退出）；清空逻辑全部内嵌在本文件，不依赖其它脚本
setlocal enableextensions
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
rem 证书：Windows 上 Python 默认没有 CA 包，指向 certifi 的根证书，避免访问 GitHub API 报证书错误
if exist "%~dp0.venv\Lib\site-packages\certifi\cacert.pem" set "SSL_CERT_FILE=%~dp0.venv\Lib\site-packages\certifi\cacert.pem"
if defined SSL_CERT_FILE set "REQUESTS_CA_BUNDLE=%SSL_CERT_FILE%"

if /i "%~1"=="--menu" goto menu
if /i "%~1"=="--reset-remote" goto reset_remote

:home
cls
echo.
echo  ==========================================
echo    青鸾备案项目地图  V3.0
echo  ==========================================
echo    1   打开主菜单（部署 / 抓取 / 预览 / 诊断）
echo    9   清空线上 Git 仓库（危险操作）
echo    0   退出
echo  ==========================================
set "CH="
set /p "CH=请输入编号后回车: "
if "%CH%"=="1" goto menu
if "%CH%"=="9" goto reset_remote
if "%CH%"=="0" exit /b 0
goto home

:menu
"%PY%" "%~dp0scripts\menu.py"
if errorlevel 1 pause
exit /b 0

:reset_remote
cls
echo.
echo  ============ 清空线上 Git 仓库 ============
echo.
echo  作用：删除线上仓库当前分支里的全部文件，把仓库清空。
echo        之后回到菜单 1 重新部署 V3.0，就能得到干净的文件结构。
echo.
echo  说明：
echo   - 只删文件，不改写 Git 历史，不动其它分支。
echo   - 清空后线上页面会立刻 404，Actions 也会失效，直到重新部署。
echo   - owner / repo 取自 config\config.json 的 publish 段；
echo     Token 取自 config\deploy.json 或环境变量 GITHUB_TOKEN，缺失会提示输入。
echo   - 确认前请先想清楚：仓库里需要保留的东西请先备份。
echo.
set "QL_ROOT=%~dp0"
rem 下面这条 PowerShell：读配置 -> 列线上文件 -> 要求输入 DELETE 二次确认 -> 逐个删除
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';$root=$env:QL_ROOT;if(-not $root){Write-Host 'ERR no workdir';exit 2};$owner='';$repo='';$branch='main';$tok='';$p1=Join-Path $root 'config\config.json';if(Test-Path $p1){$c=ConvertFrom-Json (Get-Content -Raw -Encoding UTF8 $p1);if($c.publish){if($c.publish.github_owner){$owner=$c.publish.github_owner};if($c.publish.github_repo){$repo=$c.publish.github_repo};if($c.publish.branch){$branch=$c.publish.branch}}};$p2=Join-Path $root 'config\deploy.json';if(Test-Path $p2){$d=ConvertFrom-Json (Get-Content -Raw -Encoding UTF8 $p2);if(-not $owner){$owner=$d.owner};if(-not $repo){$repo=$d.repo};if($d.token){$tok=$d.token}};if(-not $tok){$tok=$env:GITHUB_TOKEN};if(-not $owner){$owner=Read-Host 'GitHub owner'};if(-not $repo){$repo=Read-Host 'GitHub repo'};if(-not $tok){$tok=Read-Host 'GitHub token'};if(-not $owner -or -not $repo -or -not $tok){Write-Host 'ERR missing owner/repo/token';exit 2};$h=@{'Authorization'=('token '+$tok);'Accept'='application/vnd.github+json';'User-Agent'='qingluan-reset'};$api=('https://api.github.com/repos/'+$owner+'/'+$repo);Write-Host ('Repo: '+$owner+'/'+$repo+'  branch: '+$branch);$tree=$null;try{$tree=Invoke-RestMethod -Method Get -Uri ($api+'/git/trees/'+$branch+'?recursive=1') -Headers $h}catch{$m=$_.Exception.Message;if($m -match '409'){Write-Host 'Repo is empty already.';exit 3};Write-Host ('ERR read tree: '+$m);exit 1};$items=@();foreach($t in $tree.tree){if($t.type -eq 'blob'){$items+=$t}};Write-Host ('Files on remote: '+$items.Count);if($items.Count -eq 0){Write-Host 'Nothing to delete.';exit 3};$ans=Read-Host 'Type DELETE to confirm';if($ans -ne 'DELETE'){Write-Host 'Cancelled, nothing changed.';exit 3};$ok=0;$bad=0;foreach($it in $items){$enc='';foreach($s in $it.path.Split('/')){if($enc -ne ''){$enc=$enc+'/'};$enc=$enc+[uri]::EscapeDataString($s)};$body=ConvertTo-Json -Compress -InputObject @{message=('reset remote: '+$it.path);sha=$it.sha;branch=$branch};try{$null=Invoke-RestMethod -Method Delete -Uri ($api+'/contents/'+$enc) -Headers $h -Body $body -ContentType 'application/json';$ok++}catch{$bad++;Write-Host ('  FAIL '+$it.path+' '+$_.Exception.Message)}};Write-Host ('Deleted '+$ok+', failed '+$bad);if($bad -gt 0){exit 1};exit 0"
echo.
if errorlevel 3 goto reset_cancel
if errorlevel 1 goto reset_fail
echo  已处理完：线上仓库现在是空仓库。
echo  想恢复网站：回到菜单 1 重新部署（会自动 push 一份干净的 V3.0）。
echo.
pause
exit /b 0

:reset_cancel
echo  已取消（或仓库本来就是空的），线上没有任何改动。
echo.
pause
exit /b 0

:reset_fail
echo  有文件没删掉，看上面的 FAIL 行；常见原因是 Token 权限不足或网络抖动。
echo  可以重复执行本功能，已删掉的文件不会重复报错（会自动跳过）。
echo.
pause
exit /b 0
