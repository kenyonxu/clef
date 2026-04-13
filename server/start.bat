@echo off
cd /d "%~dp0"

set DEEPSEEK_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
set GLM_API_KEY=sk-czktxyswfrwzpatzgavlgvxrbxyakildkjtsjuvhueafoggt
set PYTHONPATH=%~dp0src
set PYTHONUNBUFFERED=1

if not exist logs mkdir logs
if exist logs\clef-server.log type nul > logs\clef-server.log
echo Starting Clef Server on :8900 ...
start "Clef Server" cmd /k "python -u -m uvicorn clef_server.app:app --host 0.0.0.0 --port 8900 --reload --log-config config/logging.json"

timeout /t 3 /nobreak >nul

echo Starting Clef Web Dev on :5173 ...
start "Clef Web" cmd /k "cd web && npm run dev"

timeout /t 5 /nobreak >nul
start "Clef Logs" powershell -NoExit -Command "Get-Content -Wait '%~dp0logs\clef-server.log'"

echo.
echo  Server: http://localhost:8900
echo  Dev:    http://localhost:5173
echo  Log:    logs\clef-server.log
echo  Stop:   run stop.bat to kill all processes
echo.
