"""
check_health.py — answer "why no trades this week?" from the live logs.

Run it ON THE MACHINE/VPS where live_trader.py runs (it reads logs/trader.log
and logs/*_state*.json). It distinguishes the three very different cases:

  A. Bot NOT RUNNING            → no recent "SESSION ... start" lines
                                   (scheduler/cron broken — fix ops, not strategy)
  B. Bot running, gates CLOSED  → sessions log "pause"/"skip" (VIX, GEX, regime)
                                   (system is working as designed — check regime)
  C. Bot running, just QUIET    → sessions run, reasons are "no sweep"/"no signal"
                                   (statistically normal — see the math below)

Expected frequency (validated backtests): the whole book fires ~100-130
trades/yr ≈ 2-2.5/week. A single ZERO-trade week has probability
e^-2.2 ≈ 11% — happens ~5 weeks per year. TWO consecutive silent weeks
≈ 1% — that's when to investigate seriously.

Usage:  python3 check_health.py [--days 14]
"""
import argparse
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

# Windows consoles default to cp1252 and crash on the status emoji — guard it
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(HERE, "logs")

# validated approximate signal rates per year (FINDINGS.md; used only for the
# "is silence normal?" math — edit if your live mix differs)
TRADES_PER_YEAR = {"S1": 11, "S2": 20, "S3": 10, "S4": 9, "S5": 30, "BTC": 35}

LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
SESSION_RE = re.compile(r"SESSION (\w+) start")
SIGNAL_RE = re.compile(r"\b(S\d|BTC|XSMOM)\b.*SIGNAL|^BTC SIGNAL")
REASON_PATTERNS = [
    ("VIX pause",        re.compile(r"pause: .*VIX|VIX too high", re.I)),
    ("GEX positive skip", re.compile(r"GEX positive")),
    ("regime pause",     re.compile(r"pause: spy_bull|not uptrend")),
    ("already in pos",   re.compile(r"in position")),
    ("no sweep/signal",  re.compile(r"no signal")),
]


def read_log_lines():
    paths = sorted(glob.glob(os.path.join(LOGDIR, "trader.log*")), reverse=True)
    if not paths:
        return None
    lines = []
    for p in paths:
        try:
            with open(p, errors="replace") as f:
                lines.extend(f.readlines())
        except Exception:
            pass
    return lines


def parse(lines, since):
    sessions = defaultdict(list)      # session -> [datetime]
    signals = []                      # (datetime, line)
    reasons = Counter()
    last_regime = None
    for ln in lines:
        m = LINE_RE.match(ln)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if "REGIME" in ln:
            last_regime = (ts, ln.strip())
        if ts < since:
            continue
        sm = SESSION_RE.search(ln)
        if sm:
            sessions[sm.group(1)].append(ts)
        if "SIGNAL" in ln and "no signal" not in ln:
            signals.append((ts, ln.strip()))
        for label, rx in REASON_PATTERNS:
            if rx.search(ln):
                reasons[label] += 1
                break
    return sessions, signals, reasons, last_regime


def state_files():
    out = []
    for p in sorted(glob.glob(os.path.join(LOGDIR, "*state*.json"))):
        age_h = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(p))).total_seconds() / 3600
        try:
            content = json.load(open(p))
        except Exception:
            content = "unreadable"
        out.append((os.path.basename(p), age_h, content))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    since = datetime.now() - timedelta(days=args.days)

    print(f"HEALTH CHECK — last {args.days} days  ({datetime.now():%Y-%m-%d %H:%M})")
    print("=" * 76)

    lines = read_log_lines()
    if lines is None:
        print(f"🔴 NO LOG FILE at {LOGDIR}/trader.log")
        print("   → the bot has never run here, or you're on the wrong machine.")
        print("   → check your scheduler (cron/Task Scheduler/schedule_mt5.ps1).")
        sys.exit(1)

    sessions, signals, reasons, last_regime = parse(lines, since)

    # A. Is the bot running?
    print("\n[1] SCHEDULER / SESSIONS (case A check)")
    if not sessions:
        print(f"  🔴 ZERO 'SESSION ... start' lines in {args.days}d — bot is NOT running.")
        print("     Fix the scheduler first; strategy strictness is irrelevant.")
    else:
        for s, ts_list in sorted(sessions.items()):
            last = max(ts_list)
            age = (datetime.now() - last).days
            flag = "🟢" if age <= 2 else ("🟡" if age <= 4 else "🔴 STALE")
            print(f"  {flag} {s:<6} runs={len(ts_list):>3}  last={last:%Y-%m-%d %H:%M} ({age}d ago)")

    # B. Are gates closing?
    print("\n[2] GATES / BLOCKING REASONS (case B check)")
    if last_regime:
        print(f"  last regime: {last_regime[1][:110]}")
    if reasons:
        for label, n in reasons.most_common():
            print(f"  {label:<18} × {n}")
        gate_blocks = reasons["VIX pause"] + reasons["GEX positive skip"] + reasons["regime pause"]
        if gate_blocks > reasons["no sweep/signal"]:
            print("  ⚠️  Gates (VIX/GEX/regime) are the main blocker → system working as")
            print("      designed in a hostile regime, NOT broken. Signals resume with regime.")
    else:
        print("  (no reason lines found — sessions may not be reaching signal checks)")

    # C. Signals & statistical normality
    print("\n[3] SIGNALS (case C check)")
    if signals:
        for ts, ln in signals[-10:]:
            print(f"  🟢 {ln[:110]}")
    else:
        lam_week = sum(TRADES_PER_YEAR.values()) / 52
        weeks = args.days / 7
        p_silent = math.exp(-lam_week * weeks)
        print(f"  0 signals in {args.days}d.")
        print(f"  Expected ≈ {lam_week:.1f} signals/week (whole book). "
              f"P(zero over {args.days}d) ≈ {p_silent:.1%}.")
        if p_silent > 0.05:
            print("  🟡 Plausibly a normal quiet patch — IF [1] is green and [2] shows")
            print("     'no sweep/no signal' rather than gate blocks.")
        else:
            print("  🔴 Statistically unlikely to be luck — investigate data feeds and gates.")
        print("  Also run: python3 verify_liveness.py  (replays real history through")
        print("  the exact entry conditions — proves the logic CAN fire on recent data).")

    # State files
    print("\n[4] STATE FILES (throttle + BTC position tracking)")
    sf = state_files()
    if not sf:
        print("  🟡 no logs/*state*.json found — dd-throttle & BTC state never initialized?")
    for name, age_h, content in sf:
        flag = "🟢" if age_h < 48 else "🟡"
        print(f"  {flag} {name:<28} updated {age_h:>5.0f}h ago  {str(content)[:60]}")

    print("\nVERDICT GUIDE: [1] red → fix scheduler. [2] dominated by gates → regime,")
    print("wait. [3] yellow + [1] green → normal sparsity; the backtest numbers ARE")
    print("consistent with silent weeks (~11% each week). Two+ silent weeks → dig in.")


if __name__ == "__main__":
    main()
