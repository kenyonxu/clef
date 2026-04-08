@echo off
set DEEPSEEK_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
set GLM_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
python -m clef_server
