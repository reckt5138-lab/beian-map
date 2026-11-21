@echo off
rem Open index.html through a local HTTP server, so the page can fetch cloud data.
rem Browser security blocks fetch from file:// ; this one-click wrapper avoids that.
cd /d "%~dp0"
set PORT=8080
start "map-server" /min cmd /c "python -m http.server %PORT% --bind 127.0.0.1"
timeout /t 2 >nul
start "" "http://127.0.0.1:%PORT%/index.html"
exit
