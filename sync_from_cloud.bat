@echo off
setlocal EnableExtensions
call "%~dp0rclone_env.bat"

if not exist "%LIFEOS_JOURNAL_ROOT%" mkdir "%LIFEOS_JOURNAL_ROOT%"

"%RCLONE_EXE%" copy "%LIFEOS_REMOTE%" "%LIFEOS_JOURNAL_ROOT%" ^
  --update ^
  --create-empty-src-dirs ^
  --exclude ".obsidian/**" ^
  --exclude ".trash/**" ^
  --log-file "%~dp0logs\rclone_from_cloud.log" ^
  --log-level INFO

endlocal
