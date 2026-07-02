# update_vps.ps1 -- ONE command to sync the VPS with GitHub main and (optionally)
# run the full validation battery. No more copy-pasting many commands into the
# wrong shell: download this file once, then always run it instead.
#
#   Update code only:      powershell -ExecutionPolicy Bypass -File update_vps.ps1
#   Update + validate:     powershell -ExecutionPolicy Bypass -File update_vps.ps1 -Validate
#   Update + reschedule:   powershell -ExecutionPolicy Bypass -File update_vps.ps1 -Schedule
#
# -Validate pulls broker-real MT5 history and runs every pending test, writing
# everything to validation_report.txt (paste that file back into the chat).

param(
    [switch]$Validate,
    [switch]$Schedule
)

# force UTF-8 python I/O (Windows cp1252 console crashes on unicode output)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$base = "https://raw.githubusercontent.com/colindayer-boop/nas100-trader/main"
$files = @(
    "live_trader.py", "broker.py", "mt5_broker.py", "alerts.py",
    "fetch_mt5_history.py", "check_health.py", "verify_liveness.py",
    "london_breakout_test.py", "intraday_momentum_test.py",
    "prop_firm_optimizer.py", "mean_reversion_test.py",
    "schedule_mt5.ps1", "perf_report.py"
)

Write-Host "=== nas100-trader VPS updater ===" -ForegroundColor Cyan
$here = $PSScriptRoot
if (-not $here) { $here = (Get-Location).Path }
Set-Location $here

$fail = 0
foreach ($f in $files) {
    try {
        Invoke-WebRequest -Uri "$base/$f" -OutFile $f -UseBasicParsing
        Write-Host ("  ok   " + $f)
    } catch {
        Write-Host ("  FAIL " + $f + "  " + $_.Exception.Message) -ForegroundColor Red
        $fail++
    }
}
if ($fail -gt 0) {
    Write-Host "$fail file(s) failed to download - check network/URL." -ForegroundColor Red
}

if ($Schedule) {
    Write-Host "`n=== registering scheduled tasks ===" -ForegroundColor Cyan
    powershell -ExecutionPolicy Bypass -File (Join-Path $here "schedule_mt5.ps1")
}

if ($Validate) {
    $report = Join-Path $here "validation_report.txt"
    Write-Host "`n=== validation battery (writing $report) ===" -ForegroundColor Cyan
    "VALIDATION REPORT  $(Get-Date)" | Out-File $report

    "`n--- 1. MT5 history bridge (US100 alias qqq, XAUUSD, EURUSD, GBPUSD) ---" |
        Tee-Object $report -Append
    python fetch_mt5_history.py --symbols US100 XAUUSD EURUSD GBPUSD --years 6 --alias qqq 2>&1 |
        Tee-Object $report -Append

    "`n--- 2. London Breakout gauntlet (the video strategy) ---" | Tee-Object $report -Append
    python london_breakout_test.py --symbols EURUSD GBPUSD 2>&1 | Tee-Object $report -Append

    "`n--- 3. Intraday momentum gauntlet (SSRN lead) on US100 CFD feed ---" |
        Tee-Object $report -Append
    python intraday_momentum_test.py 2>&1 | Tee-Object $report -Append

    "`n--- 4. Liveness replay (entry logic on broker data) ---" | Tee-Object $report -Append
    python verify_liveness.py 2>&1 | Tee-Object $report -Append

    "`n--- 5. Health check (scheduler / gates / signals) ---" | Tee-Object $report -Append
    python check_health.py 2>&1 | Tee-Object $report -Append

    "`n--- 6. MT5 timezone fix sanity (should print server-UTC offset) ---" |
        Tee-Object $report -Append
    python live_trader.py --broker mt5 --dry-run --session asian 2>&1 |
        Select-String -Pattern "offset|asian_low|no signal|SIGNAL" |
        Tee-Object $report -Append

    Write-Host "`nDONE. Paste validation_report.txt back into the chat for the verdicts." `
        -ForegroundColor Green
}
