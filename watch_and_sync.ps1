param(
    [string]$JournalRoot = "D:\LifeOS\journal",
    [int]$DebounceSeconds = 8,
    [int]$MinIntervalSeconds = 20,
    [int]$PullIntervalSeconds = 180
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SyncToScript = Join-Path $ScriptDir "sync_to_cloud.bat"
$SyncFromScript = Join-Path $ScriptDir "sync_from_cloud.bat"
$LogDir = Join-Path $ScriptDir "logs"
$LogFile = Join-Path $LogDir "watch_sync.log"
$LockFile = Join-Path $LogDir "watch_sync.lock"

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}
if (!(Test-Path $JournalRoot)) {
    New-Item -ItemType Directory -Force -Path $JournalRoot | Out-Null
}

if (Test-Path $LockFile) {
    $existingPid = (Get-Content $LockFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($existingPid -and (Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue)) {
        Write-Host "LifeOS watch sync is already running as PID $existingPid"
        exit 0
    }
}
Set-Content -Path $LockFile -Value $PID -Encoding ASCII

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

$state = @{
    Dirty = $false
    Syncing = $false
    LastChange = Get-Date
    LastSync = (Get-Date).AddYears(-1)
    LastPull = (Get-Date).AddYears(-1)
}

function Should-IgnorePath {
    param([string]$Path)
    $normalized = $Path.Replace("/", "\")
    return (
        $normalized -match "\\\.obsidian\\" -or
        $normalized -match "\\\.trash\\" -or
        $normalized -match "\\_data\\raw\\computer\\" -or
        $normalized -match "\\_data\\normalized\\" -or
        $normalized -match "\\_data\\ai\\" -or
        $normalized -match "\\_system\\logs\\" -or
        $normalized.EndsWith(".tmp") -or
        $normalized.EndsWith(".swp")
    )
}

function Mark-Dirty {
    param($EventArgs)
    if ($state.Syncing) {
        return
    }
    if (Should-IgnorePath $EventArgs.FullPath) {
        return
    }
    $state.Dirty = $true
    $state.LastChange = Get-Date
    Write-Log ("change detected: {0}" -f $EventArgs.FullPath)
}

function Run-Sync {
    if ($state.Syncing) {
        return
    }
    $now = Get-Date
    if (($now - $state.LastChange).TotalSeconds -lt $DebounceSeconds) {
        return
    }
    if (($now - $state.LastSync).TotalSeconds -lt $MinIntervalSeconds) {
        return
    }
    if (-not $state.Dirty) {
        return
    }

    $state.Syncing = $true
    $state.Dirty = $false
    $state.LastSync = Get-Date
    Write-Log "sync_to_cloud started"
    try {
        $process = Start-Process -FilePath $SyncToScript -WorkingDirectory $ScriptDir -WindowStyle Hidden -Wait -PassThru
        Write-Log ("sync_to_cloud finished with exit code {0}" -f $process.ExitCode)
    } catch {
        Write-Log ("sync_to_cloud failed: {0}" -f $_.Exception.Message)
        $state.Dirty = $true
    } finally {
        $state.Syncing = $false
    }
}

function Run-Pull {
    if ($state.Syncing) {
        return
    }
    $now = Get-Date
    if (($now - $state.LastPull).TotalSeconds -lt $PullIntervalSeconds) {
        return
    }
    if ($state.Dirty) {
        return
    }

    $state.Syncing = $true
    $state.LastPull = Get-Date
    Write-Log "sync_from_cloud started"
    try {
        $process = Start-Process -FilePath $SyncFromScript -WorkingDirectory $ScriptDir -WindowStyle Hidden -Wait -PassThru
        Write-Log ("sync_from_cloud finished with exit code {0}" -f $process.ExitCode)
    } catch {
        Write-Log ("sync_from_cloud failed: {0}" -f $_.Exception.Message)
    } finally {
        $state.Syncing = $false
    }
}

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $JournalRoot
$watcher.IncludeSubdirectories = $true
$watcher.Filter = "*.*"
$watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, DirectoryName, LastWrite, Size'
$watcher.EnableRaisingEvents = $true

$handlers = @()
$handlers += Register-ObjectEvent -InputObject $watcher -EventName Changed -Action { Mark-Dirty $Event.SourceEventArgs }
$handlers += Register-ObjectEvent -InputObject $watcher -EventName Created -Action { Mark-Dirty $Event.SourceEventArgs }
$handlers += Register-ObjectEvent -InputObject $watcher -EventName Deleted -Action { Mark-Dirty $Event.SourceEventArgs }
$handlers += Register-ObjectEvent -InputObject $watcher -EventName Renamed -Action { Mark-Dirty $Event.SourceEventArgs }

Write-Log ("watching {0}" -f $JournalRoot)
Write-Log ("debounce={0}s min_interval={1}s pull_interval={2}s" -f $DebounceSeconds, $MinIntervalSeconds, $PullIntervalSeconds)

try {
    while ($true) {
        Start-Sleep -Seconds 2
        Run-Pull
        Run-Sync
    }
} finally {
    foreach ($handler in $handlers) {
        Unregister-Event -SubscriptionId $handler.Id -ErrorAction SilentlyContinue
    }
    Remove-Item -Force $LockFile -ErrorAction SilentlyContinue
    $watcher.Dispose()
}
