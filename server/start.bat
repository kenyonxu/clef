@echo off
cd /d "%~dp0"

set DEEPSEEK_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
set GLM_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
set PYTHONPATH=%~dp0src

echo Starting Clef Server on :8900 ...
start "Clef Server" cmd /k "python -m uvicorn clef_server.app:app --host 0.0.0.0 --port 8900 --reload"

timeout /t 3 /nobreak >nul

echo Starting Clef Web Dev on :5173 ...
start "Clef Web" cmd /k "cd web && npm run dev"

echo.
echo  Server: http://localhost:8900
echo  Dev:    http://localhost:5173
echo.
