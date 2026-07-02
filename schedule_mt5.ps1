# schedule_mt5.ps1 -- register ALL bot sessions as Windows Scheduled Tasks.
# Strategies self-gate by session time, so frequent triggers are safe (demo/CFD,
# runs are cheap). Timezone-proof: repetition intervals, not wall-clock times.
#
# Save IN the same folder as live_trader.py, then run (PowerShell, as Admin):
#   powershell -ExecutionPolicy Bypass -File schedule_mt5.ps1
#
# Registers:
#   Nas100Bot-MT5        hourly     --session all        (S1+S2+S3+S4+S5+sweep)
#   Nas100Bot-Overnight  30 min     --session overnight  (Tue/Wed overnight drift)
#   Nas100Bot-BTC        hourly     --session btc        (BTC Asian sweep)
#   Nas100Bot-BTCTrend   daily      --session btctrend   (BTC Donchian trend)
#   Nas100Bot-Rebal      daily*     --session rebal      (*only fires on day 1)
#
# Keep the MT5 terminal OPEN and DISCONNECT (don't log off) the RDP session.

$folder = $PSScriptRoot
if (-not $folder) { $folder = (Get-Location).Path }
$logdir = Join-Path $folder "logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

function Register-BotTask($name, $session, $minutes, $monthGate) {
    $bat = Join-Path $folder ("run_" + $session + ".bat")
    $gate = ""
    if ($monthGate) {
        # only run on the 1st of the month (xsmom monthly rebalance)
        $gate = "for /f %%d in ('powershell -NoProfile -Command (Get-Date).Day') do if not %%d==1 exit /b 0`r`n"
    }
    $content = "@echo off`r`nset PYTHONUTF8=1`r`n" + $gate + "cd /d `"$folder`"`r`n" +
        "python live_trader.py --broker mt5 --session $session >> `"$logdir\$session.log`" 2>&1`r`n"
    Set-Content -Path $bat -Encoding ASCII -Value $content
    $action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
                -RepetitionInterval (New-TimeSpan -Minutes $minutes) `
                -RepetitionDuration (New-TimeSpan -Days 3650)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
        -RunLevel Highest -Force -Description "nas100-trader --session $session" | Out-Null
    Write-Host ("  registered " + $name + "  (every " + $minutes + " min, session " + $session + ")")
}

Write-Host "Registering bot tasks in $folder ..."
Register-BotTask "Nas100Bot-MT5"       "all"       60    $false
Register-BotTask "Nas100Bot-Overnight" "overnight" 30    $false
Register-BotTask "Nas100Bot-BTC"       "btc"       60    $false
Register-BotTask "Nas100Bot-BTCTrend"  "btctrend"  1440  $false
Register-BotTask "Nas100Bot-Rebal"     "rebal"     1440  $true

# retire the old ad-hoc task if present (replaced by Nas100Bot-Overnight)
Unregister-ScheduledTask -TaskName "Overnight-MT5" -Confirm:$false -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "DONE. Verify with:  Get-ScheduledTask -TaskName Nas100Bot*" -ForegroundColor Green
Write-Host "Logs land in $logdir\<session>.log ; triage with: python check_health.py"
Write-Host "Keep MT5 open; DISCONNECT the RDP window, do not log off."
