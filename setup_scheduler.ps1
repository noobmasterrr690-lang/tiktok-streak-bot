<#
.SYNOPSIS
    Registers the "TikTokDailyStreakBot" scheduled task in Windows Task Scheduler.
    1) Starts at User Logon in continuous headless `--watch` mode (checks every 30s and
       messages immediately the instant a streak turns unlit/inactive).
    2) Also triggers at 12:01 AM (midnight streak reset) repeating every 15 minutes
       as a fallback if the background watcher ever closes.
#>

$TaskName = "TikTokDailyStreakBot"
$ProjectDir = "C:\Users\Kier\Documents\tiktok-streak-bot"
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "main.py --headless --watch" `
    -WorkingDirectory $ProjectDir

$TriggerMidnight = New-ScheduledTaskTrigger `
    -Once `
    -At "12:01AM" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($TriggerMidnight) `
    -Settings $Settings `
    -Description "Real-time TikTok streak watcher that immediately messages any streak as soon as it becomes inactive/unlit." `
    -Force

Write-Host "`n[OK] Real-time Scheduled Task '$TaskName' registered!" -ForegroundColor Green
Write-Host "Runs in continuous --watch mode (checking every 30s) + midnight 12:01 AM / 15-min fallback triggers."
