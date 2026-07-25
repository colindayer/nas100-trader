"""deploy.py -- Deployment Manager. One authoritative manifest; verifies a complete installation
before anything is allowed to start.

    py deploy.py --manifest            # regenerate MANIFEST.json (run on the source machine)
    py deploy.py --verify              # verify THIS machine against the manifest
    py deploy.py --sync-script         # emit the SHA-pinned PowerShell sync for the VPS

Why SHA-pinned URLs: raw.githubusercontent.com caches by path and IGNORES ?v= query strings, so
"cache-busted" downloads silently return stale files. A commit-SHA URL is immutable.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, "MANIFEST.json")
REPO = "colindayer/nas100-trader"

TRACKED = [
    "VERSION.json", "healthcheck.py", "deploy.py", "startup.py",
    "scripts/portfolio_mt5.py", "scripts/prop_risk_guardian.py",
    "execution_safety/__init__.py", "execution_safety/gate.py",
    "execution_safety/strategy_contract.py", "execution_safety/execution_guard.py",
    "execution_safety/belief_graph_v2.py", "execution_safety/promotion_pipeline_v2.py",
    "execution_safety/operational_belief.py", "execution_safety/demo_evidence.py",
    "execution_safety/position_ledger.py", "execution_safety/broker_reconciliation.py",
    "execution_safety/guardian_bridge.py", "execution_safety/belief_reader.py",
    "execution_safety/shadow.py", "execution_safety/promotion_gate.py",
    "market_intel/__init__.py", "market_intel/state.py", "market_intel/calendar_feed.py",
    "market_intel/calendar_provider.py", "market_intel/faireconomy_provider.py",
    "market_intel/fred_provider.py", "market_intel/opportunity.py", "market_intel/engine.py",
    "market_intel/dashboard.py", "market_intel/web.py", "market_intel/telegram_notifier.py",
    "market_intel/tradingview_bridge.py", "market_intel/reaction_recorder.py",
    "strategy_contracts/portfolio_multisleeve.json",
]


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def build_manifest():
    files, missing = {}, []
    for rel in TRACKED:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            files[rel] = {"sha256_16": _sha(p), "bytes": os.path.getsize(p)}
        else:
            missing.append(rel)
    m = {"commit": _commit(), "files": files, "missing_at_build": missing,
         "n_files": len(files)}
    json.dump(m, open(MANIFEST, "w"), indent=1)
    return m


def verify(strict=False):
    """Return (ok, report). Missing/changed files are reported explicitly, never inferred."""
    if not os.path.exists(MANIFEST):
        return False, {"error": "MANIFEST.json not present — run --manifest on the source machine"}
    m = json.load(open(MANIFEST))
    missing, changed, ok = [], [], []
    for rel, meta in m["files"].items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            missing.append(rel); continue
        if _sha(p) != meta["sha256_16"]:
            changed.append(rel)
        else:
            ok.append(rel)
    local = _commit()
    return (not missing and (not changed or not strict)), {
        "manifest_commit": m.get("commit"), "local_commit": local,
        "commit_match": (local == m.get("commit")) if local else None,
        "n_ok": len(ok), "missing": missing, "changed": changed,
        "verdict": ("COMPLETE" if not missing and not changed else
                    "INCOMPLETE" if missing else "MODIFIED")}


def sync_script(commit=None):
    c = commit or _commit()
    if not c:
        return "# no commit available — run on a machine with git"
    base = f"https://raw.githubusercontent.com/{REPO}/{c}"
    dirs = sorted({os.path.dirname(f) for f in TRACKED if os.path.dirname(f)})
    lines = [f'# SHA-pinned sync for commit {c[:12]} (immutable - never serves a stale file)',
             f'$S="{base}"',
             f'mkdir {",".join(dirs)},registry,config -Force | Out-Null']
    for d in dirs + [""]:
        group = [f for f in TRACKED if os.path.dirname(f) == d]
        if not group:
            continue
        names = ",".join(f'"{os.path.basename(f)}"' for f in group)
        if d:
            lines.append(f'{names} | % {{ iwr "$S/{d}/$_" -OutFile "{d.replace("/", chr(92))}\\$_" }}')
        else:
            for f in group:
                lines.append(f'iwr "$S/{f}" -OutFile {f}')
    lines += ['iwr "$S/config/guardian.env" -OutFile "config\\guardian.env"',
              'py deploy.py --verify',
              'py healthcheck.py']
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--sync-script", action="store_true")
    ap.add_argument("--strict", action="store_true", help="treat modified files as failure")
    a = ap.parse_args()
    if a.manifest:
        m = build_manifest()
        print(f"MANIFEST.json: {m['n_files']} files @ commit {(m['commit'] or '?')[:12]}")
        if m["missing_at_build"]:
            print(f"  WARNING missing at build: {m['missing_at_build']}")
    elif a.sync_script:
        print(sync_script())
    else:
        ok, r = verify(strict=a.strict)
        if "error" in r:
            print(f"FAIL {r['error']}"); sys.exit(1)
        print(f"DEPLOYMENT: {r['verdict']}")
        print(f"  manifest commit : {(r['manifest_commit'] or '?')[:12]}")
        print(f"  local commit    : {(r['local_commit'] or 'n/a (file-sync deployment)')[:12]}")
        print(f"  files verified  : {r['n_ok']}/{r['n_ok']+len(r['missing'])+len(r['changed'])}")
        if r["missing"]:
            print(f"  MISSING ({len(r['missing'])}): {', '.join(r['missing'][:8])}")
        if r["changed"]:
            print(f"  MODIFIED ({len(r['changed'])}): {', '.join(r['changed'][:8])}")
        print("  -> run: py deploy.py --sync-script   (on the source machine) to regenerate the sync")
        sys.exit(0 if ok else 1)
