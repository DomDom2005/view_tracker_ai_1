@echo off
rem Uruchamia aplikację view_tracker_ai_1 (Windows, dwuklik).
cd /d "%~dp0"
python run.py %*
if errorlevel 1 pause
