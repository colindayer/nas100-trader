# sync_mt5_evidence.ps1 -- Phase 4 idempotent VPS -> private-repo sync. RUN ON THE VPS.
# Runs the read-only exporter, validates the manifest, then commits+pushes ONLY the new
# evidence dir to the PRIVATE repo. Never force-pushes, never deletes history, never
# commits unrelated files. Lock prevents overlap. GitHub down -> keep local, exit non-zero.
#
#   powershell -ExecutionPolicy Bypass -File sync_mt5_evidence.ps1 `
#       -Repo "C:\path\to\nas100-trader" -Evidence "C:\path\to\nas100-live-evidence" `
#       -Python "C:\path\to\python.exe"
param(
  [Parameter(Mandatory=$true)][string]$Repo,       # trading repo (source of exporter)
  [string]$Evidence = "C:\Users\Administrator\Documents\nas100-live-evidence",   # PRIVATE evidence repo (git clone)
  [Parameter(Mandatory=$true)][string]$Python      # interpreter proven to reach MT5 (Phase 1)
)
$ErrorActionPreference = "Stop"
$env:GIT_TERMINAL_PROMPT = "0"           # never block on credentials
$log = Join-Path $Evidence "sync.log"
function Log($m){ "$(Get-Date -Format s)  $m" | Tee-Object -FilePath $log -Append }

# --- single-instance lock ---------------------------------------------------
$lock = Join-Path $env:TEMP "nas100-evidence-sync.lock"
if (Test-Path $lock) {
  $age = (Get-Date) - (Get-Item $lock).LastWriteTime
  if ($age.TotalMinutes -lt 30) { Log "another sync is running (lock $($age.TotalMinutes)m) -- exit"; exit 0 }
}
New-Item -ItemType File -Path $lock -Force | Out-Null
try {
  $today = Get-Date -Format "yyyy-MM-dd"
  Log "export start $today"

  # 1. run the READ-ONLY exporter with the verified interpreter
  & $Python (Join-Path $Repo "scripts\ops\export_mt5_evidence.py") --out $Evidence
  if ($LASTEXITCODE -ne 0) { Log "exporter exit $LASTEXITCODE (kept local)"; exit 2 }

  # 2. validate the manifest + checksums before committing
  & $Python (Join-Path $Repo "scripts\ops\verify_manifest.py") (Join-Path $Evidence "daily\$today")
  if ($LASTEXITCODE -ne 0) { Log "manifest/checksum validation FAILED -- not committing"; exit 3 }

  # 3-7. commit ONLY the new evidence dir to the private repo
  Push-Location $Evidence
  try {
    git pull --ff-only 2>&1 | Out-Null           # safe, non-interactive
    git add -- "daily/$today" "reports/" 2>&1 | Out-Null   # ONLY evidence paths
    $changed = (git status --porcelain -- "daily/$today" "reports/")
    if ([string]::IsNullOrWhiteSpace($changed)) { Log "no new evidence content -- nothing to commit"; exit 0 }
    git commit -m "evidence $today" -- "daily/$today" "reports/" 2>&1 | Out-Null
    git push origin HEAD 2>&1 | Out-Null          # never --force
    if ($LASTEXITCODE -ne 0) { Log "push failed (GitHub down?) -- local commit preserved, retry next run"; exit 4 }
    Log "pushed evidence $today OK"
  } finally { Pop-Location }
}
catch { Log "ERROR: $_"; exit 5 }
finally { Remove-Item $lock -Force -ErrorAction SilentlyContinue }
