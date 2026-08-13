"""DAILY DESK REVIEW — reconstruct the day, extract lessons, rank bots, propose patches.

    py daily_review.py                 today
    py daily_review.py --date 2026-08-12

Writes DAILY_TRADING_REVIEW.md and PATCHES.md. Reconstructs; does not summarise: every
trade and every REFUSAL is reproduced with the reason it happened.

PATCHES.md IS A PROPOSAL. This script never edits production code.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Windows consoles default to cp1252, which cannot encode arrows or box characters. A report
# that dies on an encoding error after a full day of trading loses the day's analysis, so both
# the console and every file write are pinned to UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
TRADES = ROOT / "data" / "challenge" / "trades.jsonl"
LOGDIR = ROOT / "data" / "challenge"
OUT = ROOT / "DAILY_TRADING_REVIEW.md"
PATCHES = ROOT / "PATCHES.md"

RETCODES = {
    10027: ("CLIENT_DISABLES_AT", "AutoTrading is off in the MT5 terminal", "HIGH"),
    10018: ("MARKET_CLOSED", "market closed for this symbol", "LOW"),
    10019: ("NO_MONEY", "insufficient free margin for the requested volume", "HIGH"),
    10016: ("INVALID_STOPS", "stop/target violate the broker's minimum distance", "HIGH"),
    10014: ("INVALID_VOLUME", "volume below min, above max, or off the step", "HIGH"),
    10015: ("INVALID_PRICE", "price no longer valid -- quote moved before the order landed", "MED"),
    10004: ("REQUOTE", "price moved; broker requoted", "MED"),
    10006: ("REJECT", "broker rejected the request", "HIGH"),
    10030: ("INVALID_FILL", "filling mode not supported by this symbol", "HIGH"),
    10009: ("DONE", "filled", None),
}


def rows() -> list:
    if not TRADES.exists():
        return []
    return [json.loads(l) for l in TRADES.read_text(encoding="utf-8").splitlines() if l.strip()]


def day_slice(all_rows, date_str):
    opens = [r for r in all_rows
             if r.get("kind") != "close" and r.get("timestamp", "").startswith(date_str)]
    closes = {r["intent_id"]: r for r in all_rows if r.get("kind") == "close"}
    return opens, closes


def reconstruct(o, closes) -> dict:
    c = closes.get(o["intent_id"], {})
    rc = o.get("retcode")
    name, meaning, sev = RETCODES.get(rc, (str(rc), "unrecognised broker code", "MED"))
    filled = bool(o.get("ticket")) and rc == 10009
    return {**o, "close": c, "filled": filled, "rc_name": name, "rc_meaning": meaning,
            "rc_severity": sev}


def lesson_for(t) -> str:
    """What prevented success, or what produced it. One explicit cause per trade."""
    if not t["filled"]:
        return f"NOT FILLED — {t['rc_name']}: {t['rc_meaning']}"
    c = t["close"]
    if not c:
        return "OPEN — still live at review time, no outcome yet"
    R, sl = c.get("R"), (t.get("feature_snapshot") or {}).get("sl_dist")
    slip = abs(t.get("actual_slippage") or 0)
    swap = c.get("swap") or 0
    mfe, mae = c.get("mfe_R"), c.get("mae_R")
    if sl and slip > 0.1 * sl:
        return f"EXECUTION — slippage {slip:.2f} was {slip/sl:.0%} of the stop"
    if R is not None and R < 0 and mfe is not None and mfe > 0.8:
        return (f"TIMING/TARGET — reached {mfe:+.2f}R in favour before stopping out; "
                f"the target was never the binding constraint, the give-back was")
    if R is not None and R > 0 and mae is not None and mae < -0.7:
        return (f"SURVIVED — went {mae:+.2f}R against first; a tighter stop would have "
                f"converted this winner into a loser")
    if swap < 0 and R is not None and abs(swap) > 0.05 * abs(R or 1):
        return f"FINANCING — swap {swap:+.2f} was material against R {R:+.3f}"
    if R is None:
        return "INCOMPLETE — closed but R could not be computed"
    return f"{'WIN' if R > 0 else 'LOSS'} as expected — R {R:+.3f}, no execution anomaly"


def patches(day, all_rows) -> list:
    """Evidence -> root cause -> proposal. Never applied automatically."""
    out = []
    rejects = Counter(t["rc_name"] for t in day if not t["filled"])
    for name, n in rejects.most_common():
        ex = next(t for t in day if t["rc_name"] == name and not t["filled"])
        sev = ex["rc_severity"]
        if name == "CLIENT_DISABLES_AT":
            out.append({
                "problem": f"{n} order(s) refused: AutoTrading disabled in the terminal",
                "evidence": f"retcode 10027 on {', '.join(sorted({t['strategy_id'] for t in day if t['rc_name']==name}))}",
                "root_cause": "MT5 terminal-level AlgoTrading toggle is off; the Python API "
                              "cannot override it and the desk cannot detect it before sending",
                "patch": "Tools > Options > Expert Advisors > 'Allow algorithmic trading' so "
                         "it survives restart. Additionally: probe terminal_info().trade_allowed "
                         "at startup and HALT loudly rather than burning daily attempts.",
                "expected": "Removes an entire class of silent no-trade days",
                "confidence": "HIGH — retcode is unambiguous"})
        elif name == "INVALID_STOPS":
            out.append({
                "problem": f"{n} order(s) refused for stop distance",
                "evidence": f"e.g. {ex['strategy_id']} stop {abs(ex['entry']-ex['stop']):.2f}",
                "root_cause": "stop inside the broker's stops_level for the symbol",
                "patch": "read symbol_info().trade_stops_level and widen or skip before sending",
                "expected": "converts rejections into either valid orders or explicit skips",
                "confidence": "HIGH"})
        elif sev in ("HIGH", "MED"):
            out.append({
                "problem": f"{n} order(s) refused: {name}",
                "evidence": f"{ex['strategy_id']} at {ex['timestamp']}",
                "root_cause": ex["rc_meaning"],
                "patch": "add a pre-send validation for this condition",
                "expected": "fewer wasted daily attempts",
                "confidence": "MED"})

    # late entries: the live bot must reproduce the tested behaviour
    for t in day:
        fs = t.get("feature_snapshot") or {}
        m = fs.get("minutes_since_entry")
        if t["filled"] and m is not None and m > 30:
            out.append({
                "problem": f"{t['strategy_id']} entered {m} minutes after its window opened",
                "evidence": f"intent {t['intent_id']} at {t['timestamp']}",
                "root_cause": "controller re-fires while price sits beyond the level; the "
                              "frozen backtest takes the FIRST crossing only",
                "patch": "first-break-only guard (shipped) — verify no further late entries",
                "expected": "live record becomes evidence about the tested strategy",
                "confidence": "HIGH — backtest and live logic differed provably"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    try:
        import pandas as pd
        date = a.date or pd.Timestamp.now(tz="Europe/London").date().isoformat()
    except Exception:
        date = a.date or datetime.now(timezone.utc).date().isoformat()

    allr = rows()
    opens, closes = day_slice(allr, date)
    day = [reconstruct(o, closes) for o in opens]

    import sys
    sys.path.insert(0, str(ROOT))
    try:
        from trading_brain import belief, execution_quality, allocation, learn, events
        from challenge_controller import BOTS
        learn()
        bots = [{"strategy_id": b.strategy_id, "prior_exp": b.prior_expectancy_R,
                 "prior_n": b.prior_n, "stage": b.stage, "symbol": b.symbol} for b in BOTS]
        bels = [belief(b["strategy_id"], b["prior_exp"], b["prior_n"]) for b in bots]
        alloc = allocation(bels)
        execq = {b["strategy_id"]: execution_quality(b["strategy_id"]) for b in bots}
    except Exception as e:
        bots, bels, alloc, execq = [], [], {}, {}
        print(f"  (brain unavailable: {e})")

    L = []
    L.append(f"# DAILY TRADING REVIEW — {date}\n")
    L.append(f"_generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_\n")

    filled = [t for t in day if t["filled"]]
    rejected = [t for t in day if not t["filled"]]
    L.append(f"\n## 1. The day\n")
    L.append(f"- signals generated: **{len(day)}**")
    L.append(f"- filled: **{len(filled)}**   rejected: **{len(rejected)}**")
    closed_today = [t for t in filled if t["close"]]
    L.append(f"- closed: **{len(closed_today)}**   still open: **{len(filled)-len(closed_today)}**")
    if closed_today:
        tot = sum(t["close"].get("R") or 0 for t in closed_today)
        L.append(f"- net R today: **{tot:+.3f}**")
    if not day:
        L.append("\n**No signals at all today.** If a window was open, that is itself the "
                 "finding — check the controller ran and had data.")

    L.append(f"\n## 2. Trade-by-trade reconstruction\n")
    if not day:
        L.append("_nothing to reconstruct_")
    for t in day:
        fs = t.get("feature_snapshot") or {}
        c = t["close"]
        L.append(f"\n### {t['strategy_id']} — {t['timestamp']}")
        L.append(f"| field | value |\n|---|---|")
        L.append(f"| intent | `{t['intent_id']}` |")
        L.append(f"| symbol / side | {t['symbol']} {'LONG' if t['side']>0 else 'SHORT'} |")
        L.append(f"| signal reason | {', '.join(t.get('reason_codes') or [])} |")
        L.append(f"| entry / stop / target | {t['entry']:.2f} / {t['stop']:.2f} / {t['target']:.2f} |")
        L.append(f"| risk | {t['risk_pct']:.3%} · {t['volume']} lots |")
        L.append(f"| spread at signal | {t.get('spread', float('nan')):.2f} |")
        L.append(f"| minutes after window open | {fs.get('minutes_since_entry', '—')} |")
        L.append(f"| D1 trend | {fs.get('d1_trend', 'not recorded')} "
                 f"(vs prev day: {fs.get('d1_vs_prev_day', '—')}) |")
        L.append(f"| broker | **{t['rc_name']}** — {t['rc_meaning']} |")
        if t["filled"]:
            L.append(f"| fill / slippage | {t.get('fill')} / {t.get('actual_slippage')} |")
        if c:
            L.append(f"| exit / outcome | {c.get('exit')} / **{c.get('outcome')}** |")
            L.append(f"| gross / swap / comm / net | {c.get('gross'):+.2f} / {c.get('swap'):+.2f} "
                     f"/ {c.get('commission'):+.2f} / **{c.get('net'):+.2f}** |")
            L.append(f"| MFE / MAE | {c.get('mfe_R')} R / {c.get('mae_R')} R |")
            L.append(f"| holding | {c.get('holding_minutes')} min |")
            L.append(f"| **net R** | **{c.get('R'):+.3f}** |")
        L.append(f"\n**Lesson:** {lesson_for(t)}")

    L.append(f"\n## 3. Why the other bots did not trade\n")
    L.append("_no-entry reasons are printed live by the controller; bots with no row here "
             "generated no signal today._\n")
    silent = [b["strategy_id"] for b in bots
              if b["strategy_id"] not in {t["strategy_id"] for t in day}]
    for sid in silent:
        L.append(f"- `{sid}` — no signal")

    L.append(f"\n## 4. Bot scoreboard\n")
    L.append("| bot | n | post. exp R | t | confidence | avg slip/R | swap paid | alloc | action |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for b, be in zip(bots, bels):
        eq = execq.get(b["strategy_id"], {})
        t_ = be.get("t")
        slip = eq.get("slip_R")
        n = be["n"]
        if n == 0:
            action = "EXPERIMENTAL — no evidence"
        elif n >= 25 and t_ is not None and t_ <= -1.5:
            action = "RETIRE"
        elif n >= 40 and t_ is not None and t_ >= 1.5:
            action = "PROMOTE"
        elif n >= 25 and t_ is not None and t_ < 0:
            action = "REDUCE"
        else:
            action = "KEEP"
        L.append(f"| {b['strategy_id']} | {n} | {be['exp']:+.3f} | "
                 f"{f'{t_:+.2f}' if t_ is not None else '—'} | {be['weight_live']:.0%} | "
                 f"{f'{slip:.3f}' if slip is not None else '—'} | "
                 f"{eq.get('swap_paid', 0):+.2f} | {alloc.get(b['strategy_id'],0):.0%} | "
                 f"**{action}** |")
    if all(be["n"] == 0 for be in bels):
        L.append("\n> Every number above is prior, i.e. assumption. No bot has closed a "
                 "live trade yet, so no ranking here carries evidence.")

    pl = patches(day, allr)
    L.append(f"\n## 5. Recommended patches\n")
    L.append(f"See `PATCHES.md` — **{len(pl)}** proposed, none applied.")

    L.append(f"\n## 6. Tomorrow's priorities\n")
    pri = []
    if any(t["rc_name"] == "CLIENT_DISABLES_AT" for t in day):
        pri.append("Confirm AlgoTrading survives a terminal restart")
    if len(filled) == 0 and len(day) > 0:
        pri.append("No fills today — execution is the binding constraint, not strategy")
    if any((t.get("feature_snapshot") or {}).get("minutes_since_entry", 0) > 30
           for t in filled):
        pri.append("Verify the first-break guard prevents further late entries")
    live_bots = sum(1 for be in bels if be["n"] > 0)
    if live_bots < 5:
        pri.append(f"Only {live_bots} bot(s) have live evidence — the desk needs "
                   f"independent observations more than it needs a better bot")
    pri.append("Bot factory: one new non-correlated candidate")
    for p in pri:
        L.append(f"- {p}")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8-sig")

    P = [f"# PATCHES — proposed {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n",
         "Proposals only. Nothing here has been applied to production.\n"]
    for i, p in enumerate(pl, 1):
        P.append(f"\n## {i}. {p['problem']}\n")
        P.append(f"- **Evidence:** {p['evidence']}")
        P.append(f"- **Root cause:** {p['root_cause']}")
        P.append(f"- **Patch:** {p['patch']}")
        P.append(f"- **Expected improvement:** {p['expected']}")
        P.append(f"- **Confidence:** {p['confidence']}")
    if not pl:
        P.append("\n_No execution defects detected today._")
    PATCHES.write_text("\n".join(P) + "\n", encoding="utf-8-sig")

    print(f"wrote {OUT.name} ({len(day)} signals, {len(filled)} filled) "
          f"and {PATCHES.name} ({len(pl)} patches)")


if __name__ == "__main__":
    main()
