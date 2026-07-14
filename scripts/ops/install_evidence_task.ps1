# install_evidence_task.ps1 -- Phase 5. RUN ON THE VPS (Administrator PowerShell).
# Registers `nas100-evidence-export`, INDEPENDENT of trading / nas100-update / watchdog.
# A failure here never touches trading. Uses an interactive account (NOT SYSTEM) because
# SYSTEM typically cannot see the live MT5 terminal (confirm with probe_vps_env.py first).
#
#   powershell -ExecutionPolicy Bypass -File install_evidence_task.ps1 `
#       -Repo "C:\...\nas100-trader" -Evidence "C:\...\nas100-live-evidence" `
#       -Python "C:\...\python.exe" -RunUser "ALPHAZONE\Administrator"
param(
  [Parameter(Mandatory=$true)][string]$Repo,
  [string]$Evidence = "C:\Users\Administrator\Documents\nas100-live-evidence",
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$RunUser,   # account proven to reach MT5 (Phase 1)
  [string]$Time1 = "16:20",                        # after the final US session
  [string]$Time2 = "23:20"                         # optional, after overnight
)
# schtasks legitimately returns non-zero for the FIRST install: `schtasks /query /tn <name>`
# on a not-yet-existing task exits 1 + writes "ERROR: The system cannot find the task
# specified" to stderr. Under Stop (Windows PowerShell 5.1) that native stderr/non-zero
# THREW and aborted the bootstrap. Use Continue so 'task not found' is the normal case and
# WE decide via $LASTEXITCODE; the explicit `throw` on a genuine create failure still fires
# (throw is always terminating regardless of $ErrorActionPreference).
$ErrorActionPreference = "Continue"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false   # PS7-safe; no-op on 5.1
}
$sync = Join-Path $Repo "scripts\ops\sync_mt5_evidence.ps1"
# schtasks /tr is capped at 261 chars; the full 'powershell ... -File ... -Repo ...
# -Evidence ... -Python ...' command exceeds it with these long paths. Write a short
# launcher .cmd (in the user profile -- NOT inside a git repo, so it never dirties a
# working tree) that holds the long command, and point the task at that short path.
$launcher = Join-Path $env:USERPROFILE "nas100-evidence-task.cmd"
@"
@echo off
powershell -ExecutionPolicy Bypass -File "$sync" -Repo "$Repo" -Evidence "$Evidence" -Python "$Python"
"@ | Out-File -FilePath $launcher -Encoding ascii -Force
Write-Host "  launcher: $launcher" -ForegroundColor DarkGray
$action = "`"$launcher`""   # short -> well under the 261-char /tr limit

# /IT = run only when $RunUser is logged on (interactive) -> NO stored password needed
# and matches MT5's need for the live desktop session (same mode as the trading tasks).
# /RL LIMITED = no elevation (read-only export). Idempotent: delete then create /f.
function New-EvidenceTask($name, $time) {
  # exit 0 = task exists (delete first); non-zero = 'not found' = normal first install
  schtasks /query /tn $name *> $null
  if ($LASTEXITCODE -eq 0) {
    schtasks /delete /tn $name /f *> $null
  } else {
    Write-Host "  $name not present yet -- creating fresh (normal on first install)" -ForegroundColor DarkGray
  }
  schtasks /create /tn $name /sc DAILY /st $time /ru $RunUser /it /rl LIMITED /tr $action /f
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  /it create failed for $name; retrying without /rl..." -ForegroundColor Yellow
    schtasks /create /tn $name /sc DAILY /st $time /ru $RunUser /it /tr $action /f
  }
  if ($LASTEXITCODE -ne 0) { throw "failed to register $name (exit $LASTEXITCODE)" }
}
New-EvidenceTask "nas100-evidence-export"   $Time1
New-EvidenceTask "nas100-evidence-export-2" $Time2

Write-Host "Registered nas100-evidence-export ($Time1) + -2 ($Time2) as $RunUser [/it, no password]" -ForegroundColor Green
Write-Host "It is INDEPENDENT of trading tasks; an export failure cannot interrupt trading." -ForegroundColor Cyan
Write-Host "Verify:  schtasks /query /tn nas100-evidence-export /fo LIST /v | findstr /i `"Last Result Run`""
