@echo off
rem Starts view_tracker_ai_1 (Windows, double-click).
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
%PY% run.py %*
if errorlevel 1 pause
