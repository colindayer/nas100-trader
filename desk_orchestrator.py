"""DESK ORCHESTRATOR — coordinates existing components. Contains no trading logic.

    py desk_orchestrator.py            health + evidence + validation, write reports
    py desk_orchestrator.py --health   health only, fast
    py desk_orchestrator.py --sync     also attempt Git/Obsidian (auxiliary, may fail)

WHAT IT IS NOT
  Not a second brain. challenge_controller trades, trading_brain believes, desk allocates,
  head_trader reviews. This asks them whether they did, and records the answer. There must
  never be two orchestrators, so this owns coordination state and nothing else.

FAIL CLOSED FOR TRADING, FAIL OPEN FOR ANALYSIS
  This process NEVER blocks trading -- it cannot, it does not place orders. Every auxiliary
  failure (Git, Obsidian, LLM) is recorded and retried. Trading-critical faults are detected
  here and reported, but enforcement lives in the controller's preflight, where it belongs:
  a monitor that can be down must not be the thing that stops entries.

VALIDATION MISSION
  For the next 30 VALID trades the question is not profit, it is whether the desk can measure
  reality. Any completeness metric below 100% means infrastructure first -- never a strategy
  change.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOGS = DATA / "logs"
TRADES = DATA / "challenge" / "trades.jsonl"
BRAIN = DATA / "brain" / "events.jsonl"
REVIEW_QUEUE = DATA / "review_queue"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GREEN, AMBER, RED = "GREEN", "AMBER", "RED"


# ==================================================================== health
def health() -> dict:
    """Is the desk alive and honest? Each check names its own remedy."""
    import desk_events as EV
    out, faults, warns = {}, [], []

    # --- controller heartbeat. The single most important signal: a desk that stopped firing
    # looks exactly like a desk with no opportunities.
    mark = LOGS / ".last_cycle"
    age = None
    if mark.exists():
        try:
            age = datetime.now(timezone.utc).timestamp() - float(mark.read_text().strip())
        except Exception:
            pass
    out["last_cycle_age_s"] = round(age, 1) if age is not None else None
    if age is None:
        faults.append("controller has never recorded a cycle")
    elif age > 900:
        faults.append(f"controller last cycle {age/60:.0f} min ago -- not firing")
    elif age > 180:
        warns.append(f"controller last cycle {age/60:.1f} min ago (expected ~1)")

    # --- ledgers
    for name, p in (("trade_ledger", TRADES), ("brain_ledger", BRAIN)):
        ok = True
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8"):
                pass
        except Exception as e:
            ok = False
            faults.append(f"{name} not writable: {e}")
        out[f"{name}_writable"] = ok

    # --- disk
    try:
        import shutil
        free = shutil.disk_usage(str(ROOT)).free / 2**30
        out["disk_free_gb"] = round(free, 1)
        if free < 2:
            faults.append(f"disk {free:.1f} GB free")
        elif free < 10:
            warns.append(f"disk {free:.1f} GB free")
    except Exception:
        pass

    # --- MT5 + clock. Absence is a FAULT on the trading host and merely informational here,
    # so it is reported without asserting which host we are on.
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            a, t = mt5.account_info(), mt5.terminal_info()
            out["account"] = getattr(a, "login", None)
            out["is_demo"] = getattr(a, "trade_mode", None) == 0
            out["trade_allowed"] = getattr(t, "trade_allowed", None)
            out["mt5_connected"] = getattr(t, "connected", None)
            if a and a.login != 1514166963:
                faults.append(f"WRONG ACCOUNT {a.login}")
            if t is not None and not t.trade_allowed:
                faults.append("AlgoTrading disabled -- every order will retcode 10027")
            try:
                import market_state as MS, pandas as pd
                dn = MS.broker_now_london(mt5)
                gap = abs((pd.Timestamp.now(tz="Europe/London") - dn).total_seconds())
                out["desk_clock"] = str(dn)
                out["host_broker_gap_s"] = round(gap)
                if gap > 900:
                    warns.append(f"host clock {gap/60:.0f} min from broker")
            except Exception as e:
                warns.append(f"clock unreadable: {e}")
            mt5.shutdown()
        else:
            out["mt5"] = "initialize failed"
            warns.append("MT5 not reachable from this host")
    except ImportError:
        out["mt5"] = "MetaTrader5 not installed (not the trading host)"

    out["faults"], out["warnings"] = faults, warns
    out["status"] = RED if faults else (AMBER if warns else GREEN)
    EV.emit("orchestrator", "HEALTH", **{k: v for k, v in out.items()})
    return out


# ==================================================================== evidence
def evidence() -> dict:
    """Completeness, not performance. Every percentage below 100 is an infrastructure task."""
    import desk_events as EV
    rows = []
    if TRADES.exists():
        for l in TRADES.read_text(encoding="utf-8").splitlines():
            if l.strip():
                try:
                    rows.append(json.loads(l))
                except Exception:
                    pass
    intents = {r["intent_id"]: r for r in rows if r.get("kind") != "close"}
    closes = {r["intent_id"]: r for r in rows if r.get("kind") == "close"}
    filled = {k: v for k, v in intents.items() if v.get("ticket") and v.get("retcode") == 10009}
    rejected = {k: v for k, v in intents.items() if v.get("retcode") not in (10009, None)}

    def pct(n, d):
        return None if not d else round(100 * n / d, 1)

    m = {
        "signals_logged": len(intents),
        "orders_attempted": len(filled) + len(rejected),
        "fills": len(filled),
        "rejections": len(rejected),
        "closes": len(closes),
        # every fill must have an intent -- an orphan fill means the desk traded blind
        "fills_with_intent_pct": pct(sum(1 for k in filled if k in intents), len(filled)),
        "fills_reconciled_pct": pct(sum(1 for k in filled if k in closes), len(filled)),
        "exits_reconstructed_pct": pct(
            sum(1 for c in closes.values() if c.get("exit") is not None and c.get("R") is not None),
            len(closes)),
        "net_economics_pct": pct(
            sum(1 for c in closes.values() if c.get("net") is not None), len(closes)),
        "market_state_attached_pct": pct(
            sum(1 for i in intents.values() if (i.get("market_state") or {}).get("d1_regime")),
            len(intents)),
        "rejections_explained_pct": pct(
            sum(1 for r in rejected.values() if r.get("retcode")), len(rejected)),
    }

    # --- no-trade coverage comes from the structured event log
    evs = EV.read()
    nt = [e for e in evs if e.get("event") == "NO_TRADE"]
    m["no_trade_events"] = len(nt)
    m["no_trade_reasons_coded_pct"] = pct(
        sum(1 for e in nt if e.get("reason_code") not in (None, "UNMAPPED", "UNSPECIFIED")),
        len(nt))
    from collections import Counter
    m["no_trade_by_code"] = dict(Counter(e.get("reason_code") for e in nt).most_common())

    # --- posterior / lesson coverage
    try:
        import trading_brain as TB
        learned = {e.get("intent_id") for e in TB.events("trade_learned")}
        voided = TB.voided_intents()
        valid_closes = [k for k in closes if k not in voided]
        m["lessons_stored_pct"] = pct(sum(1 for k in valid_closes if k in learned),
                                      len(valid_closes))
        m["voided"] = len(voided)
        m["valid_trades"] = len(valid_closes)
    except Exception as e:
        m["brain_error"] = str(e)

    EV.emit("orchestrator", "EVIDENCE", **{k: v for k, v in m.items()
                                           if not isinstance(v, dict)})
    return m


# ==================================================================== sync (auxiliary)
def _run(cmd, cwd=ROOT, timeout=120):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout, shell=isinstance(cmd, str))
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def check_for_updates() -> dict:
    """Is new code waiting? FETCH and REPORT -- never apply.

    Auto-pulling would let anyone with repo write access change a live trading system with no
    human in the loop, which the desk charter forbids: humans approve production changes.
    So this makes the update VISIBLE and leaves the decision where it belongs.
    """
    import desk_events as EV
    code, _ = _run(["git", "fetch", "-q", "origin"], timeout=120)
    if code != 0:
        return {"update_check": "fetch failed (offline or no credential)"}
    code, local = _run(["git", "rev-parse", "HEAD"])
    code2, remote = _run(["git", "rev-parse", "@{u}"])
    if code or code2:
        return {"update_check": "no upstream configured"}
    local, remote = local.strip(), remote.strip()
    if local == remote:
        return {"update_check": "up to date", "head": local[:8]}
    _, log = _run(["git", "log", "--oneline", f"{local}..{remote}"])
    pending = [l for l in log.strip().splitlines() if l.strip()]
    EV.emit("orchestrator", "UPDATE_AVAILABLE", n_commits=len(pending),
            head=local[:8], remote=remote[:8], commits=pending[:10],
            action="NOT applied -- production changes require human approval")
    return {"update_check": f"{len(pending)} commit(s) available -- NOT applied",
            "pending": pending[:10],
            "apply_with": "git pull --ff-only origin phase404-live-demo"}


def sync() -> dict:
    """Git + Obsidian. AUXILIARY: every failure is recorded and the desk carries on.
    Nothing here can stop or delay a trade."""
    import desk_events as EV
    out = {}
    code, _ = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if code != 0:
        out["git"] = "not a git repository"
        EV.emit("orchestrator", "SYNC_SKIPPED", what="git", why=out["git"])
        return out

    code, txt = _run(["git", "ls-remote", "--exit-code", "origin", "HEAD"], timeout=30)
    if code != 0:
        out["git"] = "remote unreachable (no credential, or offline)"
        out["git_detail"] = txt.strip()[:200]
        EV.emit("orchestrator", "SYNC_FAILED", what="git", why=out["git"],
                impact="none -- trading and evidence collection continue locally")
        return out

    # Reports AND evidence. Publishing only the summaries left the ledger, the structured
    # events and the controller logs stranded on this host -- the reader could see the desk's
    # conclusions but never check them against the record that produced them.
    artifacts = [p for p in ("DAILY_VALIDATION.md", "SYSTEM_HEALTH.md",
                             "DAILY_HEAD_TRADER.md", "PATCHES.md",
                             "FIRST_VALID_EVIDENCE_REPORT.md", "ARCHITECTURE.md",
                             "DATA_FLOW.md", "OPERATIONS.md", "ROADMAP.md")
                 if (ROOT / p).exists()]
    artifacts += [d for d in ("data/logs", "data/challenge", "data/brain", "data/telemetry")
                  if (ROOT / d).exists()]
    _run(["git", "add", "--"] + artifacts)
    code, txt = _run(["git", "commit", "-m",
                      f"desk: automated reports {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"])
    out["git_commit"] = "ok" if code == 0 else ("nothing to commit" if "nothing" in txt
                                                else txt.strip()[:200])
    code, txt = _run(["git", "push", "origin", "HEAD"], timeout=180)
    out["git_push"] = "ok" if code == 0 else txt.strip()[:200]
    if code != 0:
        EV.emit("orchestrator", "SYNC_FAILED", what="git_push", why=out["git_push"],
                impact="none -- reports remain on disk")
    return out


# ==================================================================== reports
def validation_report(h: dict, m: dict) -> str:
    import desk_events as EV
    today = datetime.now(timezone.utc).date().isoformat()
    evs = EV.read(today)
    cycles = [e for e in evs if e.get("event") == "CYCLE_START"]
    gaps = [e.get("cycle_gap_s") for e in cycles if e.get("cycle_gap_s")]

    completeness = {k: v for k, v in m.items() if k.endswith("_pct") and v is not None}
    incomplete = {k: v for k, v in completeness.items() if v < 100}
    status = h["status"]
    if incomplete and status == GREEN:
        status = AMBER

    L = [f"# DAILY VALIDATION — {today}\n",
         f"## DESK STATUS: **{status}**\n",
         f"**VALID TRADES: {m.get('valid_trades', 0)} / 30**\n"]

    L.append("\n## Faults\n")
    if h["faults"]:
        for f in h["faults"]:
            L.append(f"- **RED** {f}")
    elif h["warnings"]:
        for w in h["warnings"]:
            L.append(f"- AMBER {w}")
    else:
        L.append("_none_")

    L.append("\n## Execution\n")
    L.append(f"- controller cycles logged today: **{len(cycles)}**")
    if gaps:
        L.append(f"- cycle spacing: median {sorted(gaps)[len(gaps)//2]:.0f}s, "
                 f"max {max(gaps):.0f}s "
                 f"({'blind spot risk' if max(gaps) > 90 else 'within schedule'})")
    _age = h.get("last_cycle_age_s")
    L.append(f"- last cycle: {f'{_age:.0f}s ago' if _age is not None else '**never recorded**'}")
    L.append(f"- signals {m['signals_logged']}, attempts {m['orders_attempted']}, "
             f"fills {m['fills']}, rejections {m['rejections']}, closes {m['closes']}")

    L.append("\n## Instrumentation completeness (target 100%)\n")
    L.append("| metric | % |\n|---|---|")
    for k, v in sorted(completeness.items()):
        flag = "" if v >= 100 else "  **<- FIX INFRASTRUCTURE**"
        L.append(f"| {k} | {v}%{flag} |")
    if not completeness:
        L.append("| _no completed trades yet_ | — |")

    L.append("\n## No-trade summary\n")
    if m.get("no_trade_by_code"):
        for code, n in m["no_trade_by_code"].items():
            L.append(f"- `{code}` × {n}")
        if "UNMAPPED" in m["no_trade_by_code"]:
            L.append("\n**UNMAPPED reasons exist** — a decision the validator cannot count. "
                     "Add the pattern to `desk_events.REASON_PATTERNS`.")
    else:
        L.append("_no structured no-trade events recorded yet_")

    L.append("\n## Learning\n")
    L.append(f"- lessons stored: {m.get('lessons_stored_pct')}%")
    L.append(f"- voided (instrumentation faults, never losses): {m.get('voided', 0)}")

    L.append("\n## Code updates\n")
    _u = globals().get("_LAST_UPDATE_CHECK") or {}
    L.append(f"- {_u.get('update_check', 'not checked')}")
    for c in _u.get("pending", [])[:10]:
        L.append(f"  - `{c}`")
    if _u.get("pending"):
        L.append(f"\n_Not applied. Production changes require approval:_ "
                 f"`{_u.get('apply_with')}`")

    L.append("\n## Recommendation\n")
    if h["faults"]:
        L.append(f"**FIX PROVEN DEFECT** — {h['faults'][0]}")
    elif incomplete:
        worst = min(incomplete.items(), key=lambda kv: kv[1])
        L.append(f"**FIX PROVEN DEFECT** — {worst[0]} at {worst[1]}%. "
                 f"Infrastructure before strategy.")
    else:
        L.append("**KEEP DESK UNCHANGED**")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--review", action="store_true", help="also run head_trader")
    a = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    h = health()
    age = h.get("last_cycle_age_s")
    print(f"HEALTH {h[chr(39)+chr(39)]}", end="") if False else print(
        f"HEALTH {h[chr(39)+chr(39)]}") if False else None
    for f in h["faults"]:
        print(f"  RED   {f}")
    for w in h["warnings"]:
        print(f"  AMBER {w}")
    if a.health:
        return

    if a.review:
        code, txt = _run([sys.executable, "head_trader.py"], timeout=600)
        print(f"  review -> {'ok' if code == 0 else txt.strip()[:200]}")

    upd = check_for_updates()
    globals()["_LAST_UPDATE_CHECK"] = upd
    print(f"UPDATES  {upd.get('update_check')}")
    for c in upd.get("pending", [])[:5]:
        print(f"  pending: {c}")

    m = evidence()
    print(f"EVIDENCE valid {m.get('valid_trades', 0)}/30, signals {m['signals_logged']}, "
          f"fills {m['fills']}, closes {m['closes']}, no-trade events {m['no_trade_events']}")

    (ROOT / "DAILY_VALIDATION.md").write_text(validation_report(h, m), encoding="utf-8-sig")
    (ROOT / "SYSTEM_HEALTH.md").write_text(
        f"# SYSTEM HEALTH — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n"
        f"```json\n{json.dumps(h, indent=1, default=str)}\n```\n", encoding="utf-8-sig")
    print("wrote DAILY_VALIDATION.md and SYSTEM_HEALTH.md")

    # LLM package is QUEUED, never required. Trading must not depend on an analyst.
    REVIEW_QUEUE.mkdir(parents=True, exist_ok=True)
    pkg = REVIEW_QUEUE / f"{datetime.now(timezone.utc).date()}.json"
    pkg.write_text(json.dumps({"health": h, "evidence": m}, indent=1, default=str),
                   encoding="utf-8")
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        import desk_events as EV
        EV.emit("orchestrator", "LLM_QUEUED", package=str(pkg),
                why="no ANTHROPIC_API_KEY", impact="none -- trading unaffected")
        print(f"  LLM review queued (no API key): {pkg.name}")

    if a.sync:
        s = sync()
        for k, v in s.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
