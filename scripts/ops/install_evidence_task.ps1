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
$ErrorActionPreference = "Stop"
$sync = Join-Path $Repo "scripts\ops\sync_mt5_evidence.ps1"
$action = "powershell -ExecutionPolicy Bypass -File `"$sync`" -Repo `"$Repo`" -Evidence `"$Evidence`" -Python `"$Python`""

# delete+recreate (idempotent). /RL LIMITED (no elevation needed for read-only export).
schtasks /query /tn "nas100-evidence-export" *> $null
if ($LASTEXITCODE -eq 0) { schtasks /delete /tn "nas100-evidence-export" /f | Out-Null }

schtasks /create /tn "nas100-evidence-export" /sc DAILY /st $Time1 /ru $RunUser `
  /tr $action /f | Out-Null
# second daily trigger (optional, after overnight) -- add as a repetition
schtasks /create /tn "nas100-evidence-export-2" /sc DAILY /st $Time2 /ru $RunUser `
  /tr $action /f | Out-Null

Write-Host "Registered nas100-evidence-export ($Time1) + -2 ($Time2) as $RunUser" -ForegroundColor Green
Write-Host "It is INDEPENDENT of trading tasks; an export failure cannot interrupt trading." -ForegroundColor Cyan
Write-Host "Verify:  schtasks /query /tn nas100-evidence-export /fo LIST /v | findstr /i `"Last Result Run`""
