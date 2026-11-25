@echo off
title Happenin' Web App
echo ==========================================
echo   Starting Happenin' Web App...
echo ==========================================
echo.
echo Your browser will open to http://localhost:5173/ in a few seconds.
echo Keep this window open while using the app. Close it to stop the server.
echo.
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5173/"
cd /d "%~dp0HappeninWeb"
call npm.cmd run dev
pause
