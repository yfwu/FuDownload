@echo off
REM DICOM Download + FuTransfer Wrapper - Windows Launcher

SET SCRIPT_DIR=%~dp0
REM Remove trailing backslash for consistent path handling
IF "%SCRIPT_DIR:~-1%"=="\" SET SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM Set Python paths for embedded environment
SET PYTHONPATH=%SCRIPT_DIR%\lib;%SCRIPT_DIR%\lib\site-packages
SET PYTHONNOUSERSITE=1
SET PYTHONIOENCODING=utf-8

REM Check if embedded Python exists
IF EXIST "%SCRIPT_DIR%\python\python.exe" (
    SET PYTHON_EXE=%SCRIPT_DIR%\python\python.exe
    echo Using embedded Python...
) ELSE (
    echo ERROR: Embedded Python not found!
    echo Please ensure the python folder is in the same directory as this script.
    pause
    exit /b 1
)

REM Run the wrapper with all command line arguments
"%PYTHON_EXE%" "%SCRIPT_DIR%\batch_transfer_wrapper.py" %*

IF ERRORLEVEL 1 (
    echo.
    echo Error occurred while running the wrapper.
    echo Please check the output above for details.
)

echo.
echo Press any key to exit...
pause > nul
