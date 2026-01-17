@echo off
REM Quick setup script to download Python Embedded Package
REM This script downloads and configures Python for the DICOM Download Tool

echo =========================================================
echo FuDownload - Quick Setup
echo =========================================================
echo.
echo This script downloads Python Embedded Package (10MB)
echo and configures the environment for DICOM downloading.
echo.

SET SCRIPT_DIR=%~dp0
IF "%SCRIPT_DIR:~-1%"=="\" SET SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM Check if embedded Python already exists
IF EXIST "%SCRIPT_DIR%\python\python.exe" (
    echo Python already installed in python folder!
    echo.
    echo You can now use:
    echo   run.bat                    - Interactive mode
    echo   run.bat --batch queries.csv - Batch processing
    echo   run.bat --list-servers     - List configured servers
    echo   run.bat --help             - Show all options
    exit /b 0
)

echo [1/4] Downloading Python 3.11.9 Embedded (x86 32-bit)...
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-win32.zip' -OutFile 'python-embed.zip'}"

IF ERRORLEVEL 1 (
    echo ERROR: Failed to download Python. Please check your internet connection.
    exit /b 1
)

echo [2/4] Extracting Python...
powershell -Command "Expand-Archive -Path 'python-embed.zip' -DestinationPath 'python' -Force"

IF ERRORLEVEL 1 (
    echo ERROR: Failed to extract Python archive.
    exit /b 1
)

echo [3/4] Configuring Python path settings...
REM Configure python311._pth for local package loading
echo python311.zip > python\python311._pth
echo . >> python\python311._pth
echo ..\\lib >> python\python311._pth
echo ..\\lib\\site-packages >> python\python311._pth
echo import site >> python\python311._pth

echo [4/4] Creating required directories...
REM Create logs directory if it doesn't exist
IF NOT EXIST "%SCRIPT_DIR%\logs" mkdir "%SCRIPT_DIR%\logs"

REM Create downloads directory if it doesn't exist
IF NOT EXIST "%SCRIPT_DIR%\downloads" mkdir "%SCRIPT_DIR%\downloads"

REM Clean up the downloaded zip file
del python-embed.zip

echo.
echo =========================================================
echo Setup complete!
echo.
echo The following packages are pre-installed in lib folder:
echo   - PyYAML (for configuration)
echo   - pydicom (for DICOM file handling)
echo   - pynetdicom (for DICOM network communication)
echo.
echo You can now use the tool with:
echo   run.bat                    - Interactive mode
echo   run.bat --batch queries.csv - Batch processing
echo   run.bat --list-servers     - List configured servers
echo   run.bat --help             - Show all options
echo =========================================================
echo.