@echo off
setlocal

set VENV_DIR=%~dp0.venv

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Running setup first...
    call "%~dp0setup.bat"
)

echo Starting Cisco Config Generator...
"%VENV_DIR%\Scripts\python.exe" -m cisco_config_generator %*

endlocal
