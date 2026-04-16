@echo off
echo Stopping Clef Server processes...

REM Kill by window title (set by start-server.bat)
taskkill /F /FI "WINDOWTITLE eq Clef Server*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Clef Web*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Clef Logs*" >nul 2>&1

REM Also kill by port in case started without window title (start-server.bat)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8900.*LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173.*LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo Done.
