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
    "scripts/account_forensics.py", "scripts/export_history.py",
    "execution_safety/__init__.py", "execution_safety/gate.py",
    "execution_safety/strategy_contract.py", "execution_safety/execution_guard.py",
    "execution_safety/belief_graph_v2.py", "execution_safety/promotion_pipeline_v2.py",
    "execution_safety/operational_belief.py", "execution_safety/demo_evidence.py",
    "execution_safety/position_ledger.py", "execution_safety/broker_reconciliation.py",
    "execution_safety/guardian_bridge.py", "execution_safety/belief_reader.py",
    "execution_safety/safety_state.py", "execution_safety/startup_reconciler.py",
    "execution_safety/shadow.py", "execution_safety/promotion_gate.py",
    "market_intel/__init__.py", "market_intel/state.py", "market_intel/calendar_feed.py",
    "market_intel/calendar_provider.py", "market_intel/faireconomy_provider.py",
    "market_intel/fred_provider.py", "market_intel/macro_board.py",
    "market_intel/opportunity.py", "market_intel/engine.py",
    "market_intel/dashboard.py", "market_intel/web.py", "market_intel/telegram_notifier.py",
    "market_intel/reaction_recorder.py",
    "strategy_contracts/portfolio_multisleeve.json",
]


# Components explicitly BANNED from any active execution path (caused the 61552095 incident).
BANNED_EXECUTORS = ["live_trader.py", "mt5_broker.py"]

# Modules that can place a real order. Any of these reachable from an automated trigger is an
# execution surface, whether or not it appears in BANNED_EXECUTORS.
ORDER_CAPABLE = ["live_trader.py", "mt5_broker.py", "binance_broker.py", "alpaca_broker.py",
                 "broker.py", "fill_ledger.py"]
ORDER_CALLS = ["place_order", "submit_order", "create_order", "order_send", "place_order_safe"]

# --- full execution-chain audit (Stage 4) -------------------------------------------------
# Grepping for two filenames is not an audit. A scheduled task can reach an order path via a
# .bat wrapper, a stale clone, a Downloads copy, or an MT5 terminal launch -- none of which
# contain the string "live_trader.py". Risk is therefore assessed on the WHOLE chain:
# command + arguments + working directory + which repository the path resolves into.
# A directory name at the END of a path has no trailing separator. Requiring one made
# "...\\Downloads" and "...\\trading-os" classify as HIGH instead of CRITICAL -- fail-open.
_END = r"(?:[\\/\"'\s]|$)"

RISK_PATTERNS = [
    # (regex, risk, why)
    (r"live_trader\.py|mt5_broker\.py",  "CRITICAL", "banned executor (caused the 61552095 incident)"),
    (r"run_all\.(bat|cmd|ps1)",          "CRITICAL", "legacy batch runner — chains unknown children"),
    (r"terminal64\.exe|metatrader",      "CRITICAL", "MT5 launcher — can restore Algo Trading + attached EAs"),
    (r"[\\/]Downloads" + _END,          "CRITICAL", "executes from Downloads — unversioned, unreviewed"),
    (r"[\\/](nas100_backnet|nas100-live-evidence|trading-os|kronos_lab|tradingview-mcp)" + _END,
                                          "CRITICAL", "archived/legacy repository — outside the deployment root"),
    (r"[\\/](old|bak|backup|archive|_old|copy)" + _END, "HIGH", "archived directory"),
    (r"\.bat\b|\.cmd\b",                 "MEDIUM",  "batch wrapper — actual command is indirect"),
]

# Entry points this platform is allowed to schedule, relative to the deployment root.
SANCTIONED_ENTRY = ["market_intel.web", "market_intel.reaction_recorder", "scripts\\portfolio_mt5.py",
                    "scripts/portfolio_mt5.py", "healthcheck.py", "deploy.py", "startup.py"]
APPROVED_TASKS = os.path.join(ROOT, "config", "approved_tasks.json")


def _approved():
    """Explicit operator allowlist. Absent file = nothing is pre-approved (fail closed)."""
    try:
        return set(json.load(open(APPROVED_TASKS))["approved"])
    except Exception:
        return set()


def _classify(cmd, args, workdir, root):
    blob = f"{cmd} {args} {workdir}"
    import re
    hits = [(risk, why) for pat, risk, why in RISK_PATTERNS if re.search(pat, blob, re.I)]
    if hits:
        order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
        risk, why = sorted(hits, key=lambda h: order[h[0]])[0]
        return risk, why
    # No pattern hit. Is it ours, and does it run a sanctioned entry point?
    inside = os.path.normcase(root) in os.path.normcase(f"{workdir} {cmd} {args}")
    if inside and any(e.lower() in f"{args} {cmd}".lower() for e in SANCTIONED_ENTRY):
        return "OK", "sanctioned entry point inside the deployment root"
    if re.search(r"(^|[\\/])(py|python[0-9.]*)(\.exe)?$", cmd.strip().strip('"'), re.I) \
            or re.search(r"\.py\b|\s-m\s", args, re.I):
        return "HIGH", "python execution NOT resolving to a sanctioned entry point in the deployment root"
    return "INFO", "not a python/trading execution path"


def _tasks_from_schtasks():
    """Every scheduled task with its real Exec action. XML is used because /fo LIST truncates
    arguments and omits the working directory -- both of which are where the risk hides.

    Namespaces are stripped rather than mapped: a prefix map built from the root tag broke on a
    real VPS ('prefix t not found in prefix map'), the parse raised, and the audit reported the
    host clean while a legacy trader ran hourly. Local-name matching cannot fail that way.
    """
    import re, xml.etree.ElementTree as ET
    raw = subprocess.check_output(["schtasks", "/query", "/xml", "ONE"],
                                  stderr=subprocess.DEVNULL, timeout=60)
    txt = raw.decode("utf-16-le", "ignore") if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", "ignore")
    out, errs = [], []

    def local(el):
        return el.tag.rsplit("}", 1)[-1]

    def first(root, name):
        for el in root.iter():
            if local(el) == name and (el.text or "").strip():
                return el.text.strip()
        return ""

    def tasks_in(root):
        return [root] if local(root) == "Task" else \
               [el for el in root.iter() if local(el) == "Task"]

    for chunk in re.split(r"<\\?xml[^>]*\\?>", txt):
        if "<Task" not in chunk:
            continue
        try:
            doc = ET.fromstring(chunk.strip())
        except Exception as e:
            errs.append(f"unparseable task XML: {type(e).__name__}")
            continue
        # schtasks /xml ONE emits MANY <Task> elements. Searching the whole document for URI
        # gave every action the FIRST task's name -- the report named one task 14 times and was
        # unusable for acting on. Name and Exec must be read from the SAME Task element.
        for t in tasks_in(doc):
            uri = first(t, "URI") or first(t, "Description") or "(unnamed)"
            enabled = not any(local(el) == "Enabled" and (el.text or "").strip().lower() == "false"
                              for el in t.iter())
            for ex in [el for el in t.iter() if local(el) == "Exec"]:
                g = lambda n: next((c.text.strip() for c in ex if local(c) == n and c.text), "")
                out.append({"task": uri, "enabled": enabled, "command": g("Command"),
                            "arguments": g("Arguments"), "workdir": g("WorkingDirectory")})
    if errs:
        raise RuntimeError("; ".join(errs[:3]))
    if not out:
        raise RuntimeError("schtasks returned no Exec actions — output shape unexpected")
    return out


def _autostart_entries():
    """Run keys and Startup folders -- a scheduled-task-only audit misses these entirely."""
    found = []
    for hive in ("HKCU", "HKLM"):
        for key in (r"Software\Microsoft\Windows\CurrentVersion\Run",
                    r"Software\Microsoft\Windows\CurrentVersion\RunOnce"):
            try:
                out = subprocess.check_output(["reg", "query", f"{hive}\\{key}"],
                                              stderr=subprocess.DEVNULL, timeout=20).decode("utf-8", "ignore")
            except Exception:
                continue
            for line in out.splitlines():
                p = line.split("REG_SZ")
                if len(p) == 2 and p[1].strip():
                    found.append({"task": f"{hive}\\...\\Run\\{p[0].strip()}", "enabled": True,
                                  "command": p[1].strip(), "arguments": "", "workdir": ""})
    for d in (os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
              os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup")):
        try:
            for f in os.listdir(d):
                found.append({"task": f"Startup\\{f}", "enabled": True,
                              "command": os.path.join(d, f), "arguments": "", "workdir": d})
        except Exception:
            pass
    return found


def audit_execution(root=None):
    """Stage 4: audit the ENTIRE execution chain, not just banned filenames.
    Returns (rows, errors). Every row carries task/command/args/workdir/repo/risk/action."""
    root = root or ROOT
    rows, errors = [], []
    entries = []
    for src, fn in (("scheduled_task", _tasks_from_schtasks), ("autostart", _autostart_entries)):
        try:
            for e in fn():
                e["source"] = src
                entries.append(e)
        except Exception as ex:
            errors.append(f"{src}: {type(ex).__name__}: {str(ex)[:70]} — VERIFY MANUALLY")

    approved = _approved()
    for e in entries:
        # Microsoft's own tasks are noise; keep them only if a risk pattern fires.
        risk, why = _classify(e["command"], e["arguments"], e["workdir"], root)
        is_ms = e["task"].startswith("\\Microsoft\\") or e["task"].startswith("/Microsoft/")
        if is_ms and risk in ("INFO", "OK"):
            continue
        blob = f"{e['command']} {e['arguments']} {e['workdir']}"
        repo = "(none)"
        for cand in sorted({os.path.basename(p.rstrip("\\/")) for p in
                            __import__("re").findall(r"[A-Za-z]:[\\/][^\"'\s]+", blob)}):
            if cand:
                repo = cand
                break
        low = os.path.normcase(blob)
        for marker in ("downloads", "nas100-trader-main", "nas100_backnet", "trading-os",
                       "kronos_lab", "tradingview-mcp", "nas100-live-evidence"):
            if marker in low:
                repo = marker                      # a risk path is never "the deployment root"
                break
        else:
            if os.path.normcase(root) in low:
                repo = os.path.basename(root) + " (deployment root)"
        if e["task"] in approved and risk != "CRITICAL":
            risk, why = "APPROVED", f"operator-approved in config/approved_tasks.json ({why})"
        if not e["enabled"] and risk in ("CRITICAL", "HIGH"):
            why += " [task is DISABLED — still present, can be re-enabled]"
        rows.append({**e, "repo": repo, "risk": risk, "why": why,
                     "action": {"CRITICAL": "DISABLE NOW, then delete or explicitly approve",
                                "HIGH": "investigate; disable unless justified",
                                "MEDIUM": "read the wrapper; confirm what it actually launches",
                                "APPROVED": "none — already approved",
                                "OK": "none", "INFO": "none"}[risk]})
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "APPROVED": 3, "OK": 4, "INFO": 5}
    rows.sort(key=lambda r: order[r["risk"]])
    return rows, errors


def print_execution_audit(rows, errors):
    crit = [r for r in rows if r["risk"] == "CRITICAL"]
    high = [r for r in rows if r["risk"] == "HIGH"]
    print("=" * 78)
    if crit:
        print(" CRITICAL\n\n LEGACY EXECUTION PATH DETECTED\n")
        print(" The platform must not be considered operationally clean until all legacy")
        print(" scheduled tasks are disabled or explicitly approved.")
    elif errors:
        # Never print a clean headline off an incomplete scan. The previous version did, and a
        # live hourly trader running run_all.bat out of Downloads read as "no CRITICAL detected".
        print(" INCONCLUSIVE — ENUMERATION FAILED\n")
        print(" This scan did NOT see every execution path. Absence of findings here is")
        print(" absence of evidence, not evidence of absence. Verify manually before")
        print(" treating this host as clean.")
    else:
        print(" EXECUTION CHAIN AUDIT: no CRITICAL legacy execution path detected")
    print("=" * 78)
    for r in rows:
        if r["risk"] in ("OK", "INFO"):
            continue
        print(f"\n  Task name    : {r['task']}   [{r['source']}, "
              f"{'ENABLED' if r['enabled'] else 'disabled'}]")
        print(f"  Command      : {r['command'] or '(none)'}")
        print(f"  Arguments    : {r['arguments'] or '(none)'}")
        print(f"  Working dir  : {r['workdir'] or '(not set — inherits scheduler cwd)'}")
        print(f"  Repository   : {r['repo']}")
        print(f"  Risk         : {r['risk']} — {r['why']}")
        print(f"  Action       : {r['action']}")
    clean = [r for r in rows if r["risk"] in ("OK", "APPROVED")]
    print("\n" + "-" * 78)
    print(f" {len(crit)} CRITICAL | {len(high)} HIGH | {len(clean)} sanctioned/approved | "
          f"{len(rows)} inspected")
    for e in errors:
        print(f" !! ENUMERATION INCOMPLETE — {e}")
    if errors:
        print(" A source that could not be enumerated is NOT a clean source.")
    print("=" * 78)
    return 1 if (crit or errors) else 0


def scan_execution_paths(root=None):
    """Verify no scheduler/service/startup task references a banned executor.
    Returns findings; empty = clean. Windows checks are best-effort and reported honestly."""
    import glob, subprocess
    root = root or ROOT
    findings = []
    # 1. present on disk in the deployment root?
    for b in BANNED_EXECUTORS:
        p = os.path.join(root, b)
        if os.path.exists(p):
            findings.append({"type": "BANNED_FILE_PRESENT", "file": b, "path": p})
    # 2. referenced by any .bat/.cmd/.ps1 in the root?
    for pat in ("*.bat", "*.cmd", "*.ps1"):
        for f in glob.glob(os.path.join(root, pat)):
            try:
                txt = open(f, errors="ignore").read()
            except Exception:
                continue
            for b in BANNED_EXECUTORS:
                if b in txt:
                    findings.append({"type": "BANNED_IN_SCRIPT", "file": os.path.basename(f),
                                     "references": b})
    # 3. Windows Task Scheduler (best effort; absent on non-Windows)
    try:
        out = subprocess.check_output(["schtasks", "/query", "/fo", "LIST", "/v"],
                                      stderr=subprocess.DEVNULL, timeout=25).decode("utf-8", "ignore")
        for b in BANNED_EXECUTORS:
            if b in out:
                findings.append({"type": "BANNED_IN_SCHEDULED_TASK", "references": b})
    except Exception:
        findings.append({"type": "SCHEDULER_NOT_CHECKED",
                         "detail": "schtasks unavailable (non-Windows or blocked) — verify manually"})
    # 4. running processes (best effort)
    try:
        out = subprocess.check_output(["tasklist", "/v", "/fo", "csv"],
                                      stderr=subprocess.DEVNULL, timeout=25).decode("utf-8", "ignore")
        for b in BANNED_EXECUTORS:
            if b in out:
                findings.append({"type": "BANNED_PROCESS_RUNNING", "references": b})
    except Exception:
        pass
    return findings


def scan_ci_workflows(root=None):
    """GitHub Actions is an execution surface the host scan CANNOT see.

    A cloud runner does not exist until its cron fires, so scheduled tasks, autostart entries and
    tasklist are all blind to it. A live 'Trade Workflow' running live_trader.py against a broker
    survived a CLEAN host audit for the entire project because of exactly this gap.
    """
    import glob, re
    root = root or ROOT
    out = []
    for f in glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml")):
        try:
            txt = open(f, errors="ignore").read()
        except Exception:
            continue
        crons = re.findall(r"cron:\s*[\"']([^\"']+)", txt)
        name = (re.search(r"^name:\s*(.+)$", txt, re.M) or [None, "(unnamed)"])[1].strip()
        runs = [l.strip() for l in txt.splitlines()
                if "run:" in l or re.match(r"\s*(python|py)\s", l)]
        hits = sorted({b for b in ORDER_CAPABLE if b in txt})
        # `on:` with no schedule and no dispatch is still triggerable by push
        triggered = bool(crons) or "workflow_dispatch" in txt or "push:" in txt
        out.append({"file": os.path.relpath(f, root), "name": name, "crons": crons,
                    "order_capable_refs": hits, "triggered": triggered,
                    "risk": ("CRITICAL" if hits and triggered else
                             "HIGH" if hits else "INFO"),
                    "why": ("scheduled/triggerable CI job invokes an order-capable module — "
                            "invisible to any host-based scan" if hits and triggered else
                            "references an order-capable module" if hits else
                            "no order-capable reference")})
    return out


def scan_order_surfaces(root=None):
    """Every module that can place an order, and whether anything can trigger it."""
    import glob, re
    root = root or ROOT
    surfaces = []
    for mod in ORDER_CAPABLE:
        p = os.path.join(root, mod)
        if not os.path.exists(p):
            continue
        try:
            txt = open(p, errors="ignore").read()
        except Exception:
            continue
        calls = sum(txt.count(c) for c in ORDER_CALLS)
        guarded = ("authorize(" in txt or "execution_guard" in txt or "arm(" in txt)
        surfaces.append({"module": mod, "order_calls": calls, "governed": guarded,
                         "risk": "INFO" if guarded else ("CRITICAL" if calls else "INFO"),
                         "why": ("routes through the authorization chain" if guarded
                                 else f"{calls} order call(s) with NO authorize()/execution_guard"
                                 if calls else "no order calls")})
    return surfaces


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
              'iwr "$S/MANIFEST.json" -OutFile MANIFEST.json',
              'py deploy.py --verify',
              'py healthcheck.py']
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--sync-script", action="store_true")
    ap.add_argument("--strict", action="store_true", help="treat modified files as failure")
    ap.add_argument("--scan-executors", action="store_true",
                    help="verify no scheduler/script/process references a banned executor")
    ap.add_argument("--audit-execution", action="store_true",
                    help="Stage 4: audit the ENTIRE execution chain (tasks, autostart, repos)")
    a = ap.parse_args()
    if a.audit_execution:
        rows, errors = audit_execution()
        rc = print_execution_audit(rows, errors)
        ci = scan_ci_workflows()
        surf = scan_order_surfaces()
        print("\n" + "=" * 78 + "\n CI / CLOUD EXECUTION SURFACES (host scans cannot see these)\n" + "=" * 78)
        for w in ci:
            print(f"  [{w['risk']}] {w['file']} — {w['name']}")
            print(f"      crons: {w['crons'] or 'none'}")
            print(f"      order-capable refs: {w['order_capable_refs'] or 'none'}")
            print(f"      {w['why']}")
        if not ci:
            print("  no workflow files found")
        print("\n" + "=" * 78 + "\n ORDER-CAPABLE MODULES\n" + "=" * 78)
        for m in surf:
            print(f"  [{m['risk']}] {m['module']:22s} calls={m['order_calls']:<3} "
                  f"governed={m['governed']}  {m['why']}")
        bad = [x for x in ci + surf if x["risk"] == "CRITICAL"]
        print("\n" + "-" * 78)
        print(f" {len(bad)} CRITICAL execution surface(s) outside QUANT OS governance")
        sys.exit(1 if (rc or bad) else 0)
    if a.scan_executors:
        fs = scan_execution_paths()
        hard = [f for f in fs if f["type"] != "SCHEDULER_NOT_CHECKED"]
        print("EXECUTION PATH SCAN:", "CLEAN" if not hard else f"{len(hard)} FINDING(S)")
        for f in fs:
            print(f"  {'!!' if f['type'] != 'SCHEDULER_NOT_CHECKED' else ' -'} {f}")
        if not fs:
            print("  no banned executor found on disk, in scripts, in scheduled tasks or running")
        sys.exit(1 if hard else 0)
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
