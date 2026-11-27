@echo off
title Happenin' Database Explorer
echo Refreshing Greater Boston venue & event database...
python "%~dp0HappeninIngestion\build_database.py"
echo.
echo Opening Happenin' Database Explorer...
start "" "http://localhost:5173/?view=db"
echo Make sure "Start Happenin.bat" is running if the page does not load immediately.
pause
