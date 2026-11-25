@echo off
title Refresh Happenin' Events
echo ==========================================
echo   Refreshing Happenin' Live Events...
echo ==========================================
echo.
cd /d "%~dp0HappeninIngestion"
python hybrid_collector.py
echo.
python build_web_feed.py
echo.
echo Done! Refresh http://localhost:5173/ in your browser to see the latest events.
pause
