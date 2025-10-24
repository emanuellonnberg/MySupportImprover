@echo off
REM Package script for My Support Improver Cura Plugin (Windows)
REM Creates a distributable package ready for installation

echo ========================================
echo My Support Improver - Package Builder
echo ========================================
echo.

REM Get version from plugin.json (using findstr)
for /f "tokens=2 delims=:, " %%a in ('findstr /C:"version" plugin.json') do (
    set VERSION=%%~a
    goto :found_version
)
:found_version

set PLUGIN_NAME=MySupportImprover
set PACKAGE_NAME=%PLUGIN_NAME%-%VERSION%
set BUILD_DIR=build
set PACKAGE_DIR=%BUILD_DIR%\%PLUGIN_NAME%

echo Version: %VERSION%
echo Package: %PACKAGE_NAME%.zip
echo.

REM Clean previous build
if exist "%BUILD_DIR%" (
    echo Cleaning previous build...
    rmdir /s /q "%BUILD_DIR%"
)

REM Create build directory structure
echo Creating package structure...
mkdir "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%\qt6"

REM Copy plugin files
echo Copying plugin files...
copy plugin.json "%PACKAGE_DIR%\" > nul
copy __init__.py "%PACKAGE_DIR%\" > nul
copy MySupportImprover.py "%PACKAGE_DIR%\" > nul
copy presets.json "%PACKAGE_DIR%\" > nul
copy down.svg "%PACKAGE_DIR%\" > nul
copy qt6\SupportImprover.qml "%PACKAGE_DIR%\qt6\" > nul

REM Copy documentation
echo Copying documentation...
copy README.md "%PACKAGE_DIR%\" > nul
copy CHANGELOG.md "%PACKAGE_DIR%\" > nul

REM Create the zip package (requires PowerShell)
echo Creating zip archive...
powershell -Command "Compress-Archive -Path '%BUILD_DIR%\%PLUGIN_NAME%' -DestinationPath '%BUILD_DIR%\%PACKAGE_NAME%.zip' -Force"

REM Move zip to root
move "%BUILD_DIR%\%PACKAGE_NAME%.zip" . > nul

echo.
echo [92m✓ Package created successfully![0m
echo [92m✓ File: %PACKAGE_NAME%.zip[0m
echo.

REM Display installation instructions
echo [93mInstallation Instructions:[0m
echo 1. Open Cura
echo 2. Go to: Help → Show Configuration Folder
echo 3. Navigate to the 'plugins' folder
echo 4. Extract %PACKAGE_NAME%.zip into the plugins folder
echo 5. Restart Cura
echo.

echo [93mPackage created: %PACKAGE_NAME%.zip[0m
echo.
echo Done!

pause
