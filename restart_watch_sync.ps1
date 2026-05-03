$ErrorActionPreference = "SilentlyContinue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$lockFile = Join-Path $scriptDir "logs\watch_sync.lock"
$launcher = Join-Path $scriptDir "start_watch_sync_hidden.vbs"
$logFile = Join-Path $scriptDir "logs\watch_sync.log"

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like "*watch_and_sync.ps1*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Remove-Item -Force $lockFile

wscript.exe $launcher
Start-Sleep -Seconds 5

if (Test-Path $logFile) {
    Get-Content $logFile -Tail 20
}
