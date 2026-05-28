@echo off
setlocal EnableExtensions

REM ------------------------------------------------------------------------------
REM Cisco Config Generator - Portable Launcher
REM # SPDX-License-Identifier: MIT
REM # Copyright (c) 2026 Christopher Davies
REM ------------------------------------------------------------------------------

REM === Relaunch maximised (one-time) ============================================
if not defined CCG_STARTED (
    set "CCG_STARTED=1"
    start "" /max "%ComSpec%" /c ""%~f0" %*"
    exit /b
)

REM === Normal execution continues here (in the maximised window) ================
set "ROOT=%~dp0"
set "PYTHON=%ROOT%python_runtime\python.exe"

cls
echo.
echo ================================================================================
echo                   CISCO CONFIG GENERATOR
echo                   Nautomation Prime
echo ================================================================================
echo.
echo  Starting pre-flight checks...
echo.

REM Bootstrap runtime on first run
if not exist "%PYTHON%" (
    echo  Python runtime not found - running first-time setup...
    echo.
    call "%ROOT%setup.bat"
    if errorlevel 1 (
        echo.
        echo  [FAILED] Setup did not complete. Cannot continue.
        pause
        endlocal
        exit /b 1
    )
    echo.
)

REM Check core package is present
if not exist "%ROOT%cisco_config_generator\__init__.py" (
    echo  [ERROR] Package not found: cisco_config_generator\__init__.py
    goto :error
)

REM Generate workbook template if missing
if not exist "%ROOT%assets\workbook_template.xlsx" (
    echo  Generating workbook template...
    "%PYTHON%" "%ROOT%scripts\generate_workbook.py"
    if errorlevel 1 (
        echo  [WARNING] Could not generate workbook template.
    )
)

echo  [OK] Pre-flight checks passed
echo.

pushd "%ROOT%"
"%PYTHON%" -m cisco_config_generator %*
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not %EXIT_CODE% EQU 0 (
    echo.
    echo  [ERROR] Exited with code %EXIT_CODE%.
    echo.
    pause
)

endlocal
exit /b %EXIT_CODE%

:error
echo.
echo  [FAILED] Cannot start - resolve the error above and try again.
echo.
pause
endlocal
exit /b 1
