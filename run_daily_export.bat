@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\daily_export.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

cd /d "%SCRIPT_DIR%"
call "%SCRIPT_DIR%rclone_env.bat"
call "%SCRIPT_DIR%sync_from_cloud.bat"
py -3 "%SCRIPT_DIR%daily_export.py" --skip-adb --ai-summary >> "%LOG_FILE%" 2>>&1
call "%SCRIPT_DIR%sync_to_cloud.bat"

endlocal
