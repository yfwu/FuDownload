@echo off
REM Setup script for Windows - Offline Configuration
REM This script configures the embedded Python environment for offline use

echo =========================================================
echo DICOM Download Tool - Offline Setup for Windows
echo =========================================================
echo.

SET SCRIPT_DIR=%~dp0
IF "%SCRIPT_DIR:~-1%"=="\" SET SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM Check if embedded Python exists
IF NOT EXIST "%SCRIPT_DIR%\python\python.exe" (
    echo ERROR: Embedded Python not found in python folder!
    echo Please ensure you have extracted all files correctly.
    pause
    exit /b 1
)

echo [1/3] Configuring Python path settings...

REM Create proper python311._pth file for offline use
echo python311.zip > "%SCRIPT_DIR%\python\python311._pth"
echo . >> "%SCRIPT_DIR%\python\python311._pth"
echo ..\lib >> "%SCRIPT_DIR%\python\python311._pth"
echo ..\lib\site-packages >> "%SCRIPT_DIR%\python\python311._pth"
echo import site >> "%SCRIPT_DIR%\python\python311._pth"

echo [2/3] Creating required directories...

REM Create logs directory
IF NOT EXIST "%SCRIPT_DIR%\logs" mkdir "%SCRIPT_DIR%\logs"

REM Create downloads directory
IF NOT EXIST "%SCRIPT_DIR%\downloads" mkdir "%SCRIPT_DIR%\downloads"

echo [3/3] Verifying package installation...

REM Test if packages can be imported
"%SCRIPT_DIR%\python\python.exe" -c "import yaml; print('  [OK] PyYAML found')" 2>nul
IF ERRORLEVEL 1 (
    echo   [ERROR] PyYAML not found in lib folder!
)

"%SCRIPT_DIR%\python\python.exe" -c "import pydicom; print('  [OK] pydicom found')" 2>nul
IF ERRORLEVEL 1 (
    echo   [ERROR] pydicom not found in lib folder!
)

"%SCRIPT_DIR%\python\python.exe" -c "import pynetdicom; print('  [OK] pynetdicom found')" 2>nul
IF ERRORLEVEL 1 (
    echo   [ERROR] pynetdicom not found in lib folder!
)

echo.
echo =========================================================
echo Setup complete!
echo.
echo You can now use the tool with:
echo   run.bat                    - Interactive mode
echo   run.bat --batch queries.csv - Batch processing
echo   run.bat --list-servers     - List configured servers
echo   run.bat --help             - Show all options
echo =========================================================
echo.
pause