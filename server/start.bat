@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
python -m clef_server
