@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   Cisco Config Generator - Setup
echo   Nautomation Prime
echo ============================================================
echo.

set VENV_DIR=%~dp0.venv

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [OK] Virtual environment already exists.
    goto :install_deps
)

REM Check for Python 3.10+
python --version >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Found Python %PYVER%

echo [INFO] Creating virtual environment...
python -m venv "%VENV_DIR%"
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

:install_deps
echo [INFO] Installing dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip --quiet
"%VENV_DIR%\Scripts\pip.exe" install -r "%~dp0requirements.txt" --quiet
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [OK] Setup complete!
echo [INFO] Run 'run.bat' to start the Cisco Config Generator.
echo.

endlocal
