# setup_vps_git.ps1 — one-shot VPS setup: convert the stale ZIP folder into a git
# clone that auto-pulls, and register the BTC hourly task. Run once on the VPS in
# an Administrator PowerShell. Idempotent — safe to re-run.
#
# Run it with ONE line (downloads + executes in memory, no file, no quoting traps):
#   iex (irm https://raw.githubusercontent.com/colindayer-boop/nas100-trader/main/setup_vps_git.ps1)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/colindayer-boop/nas100-trader.git"

Write-Host "== 1. locating live_trader.py ==" -ForegroundColor Cyan
$lt = Get-ChildItem C:\Users -Recurse -Filter live_trader.py -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $lt) { Write-Host "live_trader.py not found under C:\Users" -ForegroundColor Red; return }
$Repo = $lt.DirectoryName
Write-Host ("   repo folder: " + $Repo) -ForegroundColor Green
Set-Location $Repo

Write-Host "== 2. checking git ==" -ForegroundColor Cyan
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    # Windows Server has no winget — download Git for Windows and install silently
    Write-Host "   git missing. Downloading Git for Windows..." -ForegroundColor Yellow
    $url = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe"
    try {
        $rel = Invoke-RestMethod "https://api.github.com/repos/git-for-windows/git/releases/latest"
        $asset = $rel.assets | Where-Object { $_.name -match "^Git-.*-64-bit\.exe$" } | Select-Object -First 1
        if ($asset) { $url = $asset.browser_download_url }
    } catch { }
    $exe = Join-Path $env:TEMP "git-installer.exe"
    Invoke-WebRequest $url -OutFile $exe -UseBasicParsing
    Write-Host "   Installing silently (takes 1-2 min)..." -ForegroundColor Yellow
    Start-Process $exe -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP-" -Wait
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "   Git installed but PATH not refreshed. CLOSE and REOPEN PowerShell, then re-run the same one-line command." -ForegroundColor Red
        return
    }
    Write-Host "   Git installed." -ForegroundColor Green
}

Write-Host "== 3. converting folder to a git clone (config.ini is gitignored, preserved) ==" -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    git init | Out-Null
    git remote add origin $RepoUrl
} else {
    git remote set-url origin $RepoUrl 2>$null
}
git fetch origin
git reset --hard origin/main
git branch -M main
git branch --set-upstream-to=origin/main main 2>$null
Write-Host ("   now at: " + (git log -1 --oneline)) -ForegroundColor Green

Write-Host "== 4. verifying BTC symbol fix landed ==" -ForegroundColor Cyan
if (Select-String -Path .\mt5_broker.py -Pattern 'BTCUSD' -Quiet) {
    Write-Host "   OK: BTCUSD mapping present" -ForegroundColor Green
} else {
    Write-Host "   WARNING: BTCUSD not found in mt5_broker.py" -ForegroundColor Red
}

Write-Host "== 5. registering scheduled tasks ==" -ForegroundColor Cyan
$trUpdate = 'cmd /c cd /d "' + $Repo + '" && git pull'
schtasks /create /tn "nas100-update" /sc MINUTE /mo 30 /f /tr $trUpdate | Out-Null
# session tasks (all/overnight/btc/btctrend/rebal) come from schedule_mt5.ps1 —
# drop the old standalone BTC task so the hourly session does not run twice
schtasks /delete /tn "nas100-btc" /f 2>$null | Out-Null
powershell -ExecutionPolicy Bypass -File (Join-Path $Repo "schedule_mt5.ps1")
Write-Host "   nas100-update (git pull every 30 min) + Nas100Bot-* session tasks registered" -ForegroundColor Green

Write-Host "== 6. test BTC run ==" -ForegroundColor Cyan
$env:PYTHONUTF8 = "1"
python live_trader.py --broker mt5 --session btc

Write-Host ""
Write-Host "DONE. Future changes: commit+push on the Mac, VPS pulls within 30 min." -ForegroundColor Cyan
