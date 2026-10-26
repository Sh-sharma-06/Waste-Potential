@echo off
cd /d "%~dp0backend_heat_map\backend"
..\..\.venv\Scripts\uvicorn.exe main:app --port 8001 --reload
