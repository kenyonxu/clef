@echo off
set DEEPSEEK_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
set GLM_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
echo Starting Clef Server on :8900 ...
python -m uvicorn clef_server.app:app --host 0.0.0.0 --port 8900 --reload
