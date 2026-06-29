# schedule_mt5.ps1 — make the MT5 bot run automatically on the VPS.
# Registers a Windows Scheduled Task that runs the bot every hour. The strategies
# self-gate by session time, so hourly coverage catches every window regardless of
# the VPS timezone. Demo account, so frequent runs are free.
#
# Save this file IN the same folder as live_trader.py, then run:
#   powershell -ExecutionPolicy Bypass -File schedule_mt5.ps1
#
# Requirements: MT5 terminal open + logged into the demo, and you stay logged into
# the VPS (you can DISCONNECT the RDP window, just don't LOG OFF — the session and
# the task keep running).

$folder = $PSScriptRoot
if (-not $folder) { $folder = (Get-Location).Path }

# wrapper batch the task will call
$bat = Join-Path $folder "run_mt5.bat"
Set-Content -Path $bat -Encoding ASCII -Value @"
@echo off
cd /d "$folder"
python live_trader.py --broker mt5 --session all >> "$folder\mt5_run.log" 2>&1
"@
Write-Host "Wrote $bat"

# hourly trigger, indefinite
$action  = New-ScheduledTaskAction -Execute "$bat"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Hours 1) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "Nas100Bot-MT5" -Action $action -Trigger $trigger `
    -RunLevel Highest -Force `
    -Description "Runs the Nasdaq/gold bot hourly on the MT5 demo; strategies self-gate by session time."

Write-Host ""
Write-Host "DONE. Task 'Nas100Bot-MT5' runs every hour." -ForegroundColor Green
Write-Host "  - Output/log:  $folder\mt5_run.log"
Write-Host "  - To check it: open Task Scheduler -> Task Scheduler Library -> Nas100Bot-MT5"
Write-Host "  - To stop it:  Unregister-ScheduledTask -TaskName Nas100Bot-MT5 -Confirm:`$false"
Write-Host ""
Write-Host "Keep the MT5 terminal OPEN and DISCONNECT (don't log off) the RDP window."
