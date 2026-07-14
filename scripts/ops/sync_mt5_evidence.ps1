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
# git legitimately returns non-zero for detection (e.g. 'no HEAD yet'). Under Stop +
# PS7's native-error preference that would THROW ('fatal: Needed a single revision')
# and abort the bootstrap. Decouple native exit codes from Stop so WE check $LASTEXITCODE.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}
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

  # 3-7. commit ONLY the new evidence dir to the private repo (empty-repo safe)
  Push-Location $Evidence
  try {
    # ensure a commit identity exists (a freshly cloned empty repo has none).
    # capture with 2>$null so an unset key (exit 1) never surfaces as an error.
    if ([string]::IsNullOrWhiteSpace((git config user.email 2>$null))) { git config user.email "evidence-bot@nas100.local" | Out-Null }
    if ([string]::IsNullOrWhiteSpace((git config user.name  2>$null))) { git config user.name  "nas100-evidence-bot"      | Out-Null }

    # does the LOCAL repo have any commit yet?  --quiet -> NO 'fatal: Needed a single
    # revision' on an unborn HEAD (returns empty + exit 1 silently). This is the ONLY
    # revision-aware command, and it is now safe.
    $head = (git rev-parse --quiet --verify HEAD 2>$null)
    $hasCommits = -not [string]::IsNullOrWhiteSpace($head)

    if (-not $hasCommits) {
      # ---- EMPTY REPO: bootstrap main with the initial commit, then push ----
      Log "empty repository -> initializing main with the first commit"
      git symbolic-ref HEAD refs/heads/main 2>&1 | Out-Null   # unborn 'main', no commit required
      if (-not (Test-Path "README.md")) {
        "# nas100 live evidence`n`nRead-only MT5 evidence snapshots (auto-generated). Do not edit by hand." |
          Out-File -Encoding utf8 "README.md"
      }
      git add -- "README.md" "daily/$today" 2>&1 | Out-Null
      if (Test-Path "reports") { git add -- "reports" 2>&1 | Out-Null }
      git commit -m "init evidence repo + $today" 2>&1 | Out-Null
      git push -u origin main 2>&1 | Out-Null                 # creates remote main; never --force
      if ($LASTEXITCODE -ne 0) { Log "initial push failed (GitHub down?) -- local commit preserved, retry next run"; exit 4 }
      Log "initialized main + pushed evidence $today OK"
      exit 0
    }

    # ---- REPO HAS HISTORY: normal path (pull only if remote main exists, then push) ----
    git checkout main 2>&1 | Out-Null
    $remoteMain = (git ls-remote --heads origin main 2>$null)
    if (-not [string]::IsNullOrWhiteSpace($remoteMain)) { git pull --ff-only origin main 2>&1 | Out-Null }
    git add -- "daily/$today" 2>&1 | Out-Null
    if (Test-Path "reports") { git add -- "reports" 2>&1 | Out-Null }
    $changed = (git status --porcelain)
    if ([string]::IsNullOrWhiteSpace($changed)) { Log "no new evidence content -- nothing to commit"; exit 0 }
    git commit -m "evidence $today" 2>&1 | Out-Null
    git push origin main 2>&1 | Out-Null                       # upstream already set; never --force
    if ($LASTEXITCODE -ne 0) { Log "push failed (GitHub down?) -- local commit preserved, retry next run"; exit 4 }
    Log "pushed evidence $today OK"
  } finally { Pop-Location }
}
catch { Log "ERROR: $_"; exit 5 }
finally { Remove-Item $lock -Force -ErrorAction SilentlyContinue }
