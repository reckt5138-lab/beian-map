@echo off
REM Open TCP 8787 for the LAN map page. Needs admin: right-click -> Run as administrator.
REM ASCII only.
netsh advfirewall firewall add rule name="QingLuan Map 8787" dir=in action=allow protocol=TCP localport=8787
echo done
pause
