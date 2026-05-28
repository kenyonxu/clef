@echo off
setlocal enabledelayedexpansion
echo.
echo ========================================
echo   Clef -- AI Composition Dependencies
echo ========================================
echo.

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   Python: %%v

REM Create venv
set VENV_DIR=%~dp0.venv
if not exist "%VENV_DIR%" (
    echo   Creating isolated environment...
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM Activate and install
echo   Installing dependencies...
call "%VENV_DIR%\Scripts\activate.bat"
pip install -r "%~dp0requirements.txt" --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

REM Verify
echo   Verifying...
python "%~dp0skills\clef-compose\scripts\check_dependencies.py"

echo.
echo   Done! The venv is at: %VENV_DIR%
echo   To activate manually: %VENV_DIR%\Scripts\activate.bat
echo.
pause