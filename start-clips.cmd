@echo off
cd /d "%~dp0"
echo Open http://127.0.0.1:8876/clip-catalog.html
python clip-server.py
if errorlevel 1 pause
