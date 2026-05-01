@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "TASK_NAME=PersonalLifeDailyExport"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\daily_export.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher py was not found. Install Python 3 and rerun this file.
  exit /b 1
)

echo Checking Python...
py -3 --version
if errorlevel 1 (
  echo Python 3 was not found. Install Python 3 and rerun this file.
  exit /b 1
)

where adb >nul 2>nul
if errorlevel 1 (
  echo.
  echo ADB was not found in PATH. This is OK for the long-term setup.
  echo Android data should come from the Android Agent once its APK is installed.
  echo Until then, phone/pad ADB export will be skipped.
) else (
  adb version
)

echo.
echo Creating Windows scheduled task: %TASK_NAME%
set "TASK_CMD=""%SCRIPT_DIR%run_daily_export.bat"""
schtasks /Create /TN "%TASK_NAME%" /SC DAILY /ST 23:30 /TR "%TASK_CMD%" /F
if errorlevel 1 (
  echo Failed to create scheduled task.
  exit /b 1
)

echo.
echo Setup complete.
echo Test manually with:
echo   py -3 "%SCRIPT_DIR%daily_export.py"
echo Log file:
echo   %LOG_FILE%

endlocal
