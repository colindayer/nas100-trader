#!/bin/bash
# pull_live_evidence.sh -- Phase 6. Mac-side pull of the PRIVATE evidence repo.
# Read-only toward the trading repo. Never overwrites local uncommitted analysis.
#
#   ./scripts/ops/pull_live_evidence.sh [/path/to/nas100-live-evidence]
# Default evidence repo: ~/nas100-live-evidence (override via arg or $LIVE_EVIDENCE_DIR)
set -uo pipefail
EV="${1:-${LIVE_EVIDENCE_DIR:-$HOME/nas100-live-evidence}}"

if [ ! -d "$EV/.git" ]; then
  echo "EVIDENCE REPO NOT FOUND at: $EV"
  echo "  clone it first:  git clone <private nas100-live-evidence url> \"$EV\""
  exit 2
fi

cd "$EV" || exit 2
# safe pull: stash nothing of the trading repo; only fast-forward the evidence repo
if [ -n "$(git status --porcelain)" ]; then
  echo "WARNING: local changes in the evidence repo -- pulling with --ff-only (won't overwrite)"
fi
GIT_TERMINAL_PROMPT=0 git pull --ff-only 2>&1 | tail -2

# freshness + manifest validation of the latest snapshot
LATEST_DAY="$(ls -1 daily 2>/dev/null | sort | tail -1)"
if [ -z "$LATEST_DAY" ]; then echo "no daily snapshots yet"; exit 0; fi
MANIFEST="daily/$LATEST_DAY/manifest.json"
echo "latest snapshot: $LATEST_DAY"
if [ -f "$MANIFEST" ]; then
  python3 - "$MANIFEST" <<'PY'
import json,sys,datetime
m=json.load(open(sys.argv[1]))
gen=m.get("generated_at_utc","?")
try:
    age=(datetime.datetime.utcnow()-datetime.datetime.fromisoformat(gen)).total_seconds()/3600
    fresh=f"{age:.1f}h old"
except Exception: fresh="unknown age"
print(f"  status={m.get('status')} success={m.get('success')} account={m.get('account_masked')}")
print(f"  generated={gen} ({fresh}) counts={m.get('row_counts')}")
PY
else
  echo "  manifest missing for $LATEST_DAY"
fi
echo "done (trading repo untouched)."
