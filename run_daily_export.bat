@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "LIFEOS_JOURNAL_ROOT=D:\LifeOS\journal"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\daily_export.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

cd /d "%SCRIPT_DIR%"
py -3 "%SCRIPT_DIR%daily_export.py" --skip-adb --ai-summary >> "%LOG_FILE%" 2>>&1

endlocal
