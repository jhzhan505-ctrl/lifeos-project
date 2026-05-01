@echo off
setlocal EnableExtensions
call "%~dp0rclone_env.bat"

"%RCLONE_EXE%" copy "%LIFEOS_JOURNAL_ROOT%" "%LIFEOS_REMOTE%" ^
  --update ^
  --create-empty-src-dirs ^
  --exclude ".obsidian/**" ^
  --exclude ".trash/**" ^
  --log-file "%~dp0logs\rclone_to_cloud.log" ^
  --log-level INFO

endlocal
