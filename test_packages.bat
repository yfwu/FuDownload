@echo off
REM Package Test Launcher for Windows

SET SCRIPT_DIR=%~dp0
IF "%SCRIPT_DIR:~-1%"=="\" SET SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM Use embedded Python
SET PYTHON_EXE=%SCRIPT_DIR%\python\python.exe

IF NOT EXIST "%PYTHON_EXE%" (
    echo ERROR: Embedded Python not found!
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%SCRIPT_DIR%\test_packages.py"