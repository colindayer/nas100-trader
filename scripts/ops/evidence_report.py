"""evidence_report.py -- the monthly evidence report as single source of truth.

Three modes, all read-only on trading systems:
  --daily     append one evidence line per day to docs/EVIDENCE_LEDGER.md
              (shadow fire counts, live fills, ops verdict, gate states)
  --weekly    append a weekly summary block (per-stream shadow rates so far,
              slippage stats, silent-stream flags)
  --month-end generate docs/MONTH_1_LIVE_REPORT.md: research expectation vs
              forward shadow vs live execution, verdict per candidate:
              FAILS_FORWARD_EVIDENCE -> rejected | PASSES -> queued for
              post-window review. Nothing is promoted to live by this script.

Data sources (whatever exists on this host; gaps are stated, never faked):
  research/results/shadow_signals.csv     forward shadow (9 ETF survivors + gates)
  research/results/etf_streams.csv        research expectation (trades/day rates)
  logs/fills.csv                          live execution (per-host)
  docs/DAILY_OPS_REPORT.md                today's ops verdict
  state/macro_daily.csv                   regime record
"""
import argparse
import csv
import os
import re
from datetime import date, datetime

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEDGER = os.path.join(REPO, "docs", "EVIDENCE_LEDGER.md")
SHADOW = os.path.join(REPO, "research", "results", "shadow_signals.csv")
STREAMS = os.path.join(REPO, "research", "results", "etf_streams.csv")
FILLS = os.path.join(REPO, "logs", "fills.csv")
OPS = os.path.join(REPO, "docs", "DAILY_OPS_REPORT.md")
TODAY = date.today().isoformat()


def read_shadow():
    if not os.path.exists(SHADOW):
        return pd.DataFrame()
    return pd.read_csv(SHADOW)


def read_fills():
    if not os.path.exists(FILLS) or os.path.getsize(FILLS) == 0:
        return pd.DataFrame()
    return pd.read_csv(FILLS)


def ops_verdict():
    if not os.path.exists(OPS):
        return "no ops report"
    m = re.search(r"## VERDICT: \*\*(\w[\w ]*)\*\*", open(OPS, encoding="utf-8").read())
    return m.group(1) if m else "unparsed"


def ensure_ledger():
    if not os.path.exists(LEDGER):
        open(LEDGER, "w").write(
            "# EVIDENCE LEDGER\n\n_One line per day, one block per week, appended by "
            "scripts/ops/evidence_report.py. This ledger + the month-end report are "
            "the single source of truth for the go/no-go decision._\n\n"
            "| date | shadow fired/streams | live fills (host) | ops verdict | gates (lvl/ts) |\n"
            "|---|---|---|---|---|\n")


def daily():
    ensure_ledger()
    txt = open(LEDGER).read()
    if f"| {TODAY} |" in txt:
        print(f"ledger already has {TODAY} -- idempotent no-op")
        return
    sh = read_shadow()
    srow = sh[sh["date"] == TODAY] if not sh.empty else sh
    fired = int(srow["signal"].sum()) if not srow.empty else 0
    nstreams = len(srow) if not srow.empty else 0
    gates = (f"{srow['gate_vix_level'].iloc[0]}/{srow['gate_ts_ratio'].iloc[0]}"
             if not srow.empty else "-")
    fl = read_fills()
    nf = len(fl[fl["timestamp_utc"].str.startswith(TODAY)]) if not fl.empty else 0
    open(LEDGER, "a").write(
        f"| {TODAY} | {fired}/{nstreams} | {nf} | {ops_verdict()} | {gates} |\n")
    print(f"ledger + {TODAY}: shadow {fired}/{nstreams}, fills {nf}, ops {ops_verdict()}")


def weekly():
    ensure_ledger()
    sh = read_shadow()
    lines = [f"\n## Week ending {TODAY}\n"]
    if sh.empty:
        lines.append("_no shadow data yet_")
    else:
        days = sh["date"].nunique()
        per = sh.groupby("stream")["signal"].agg(["sum", "count"])
        lines.append(f"_{days} shadow days accumulated._\n")
        lines.append("| stream | fired | days | rate/day |")
        lines.append("|---|---|---|---|")
        for k, r in per.iterrows():
            lines.append(f"| {k} | {int(r['sum'])} | {int(r['count'])} | {r['sum']/max(r['count'],1):.2f} |")
        silent = per[per["sum"] == 0]
        if len(silent) and days >= 10:
            lines.append(f"\nSILENT >=10d (investigate per stream expectation): {list(silent.index)}")
    fl = read_fills()
    if not fl.empty:
        live = fl[fl.get("dry_run", "False").astype(str).str.lower() != "true"]
        s = pd.to_numeric(live.get("slippage_bps"), errors="coerce").dropna()
        lines.append(f"\nLive fills on this host: {len(live)}"
                     + (f" | slippage avg {s.mean():.1f} bps, worst {s.max():.1f}" if len(s) else " | no slippage data"))
    else:
        lines.append("\nLive fills on this host: 0 (VPS holds MT5 fills -- run there too)")
    open(LEDGER, "a").write("\n".join(lines) + "\n")
    print(f"weekly block appended ({TODAY})")


def month_end():
    sh = read_shadow()
    out = [f"# MONTH 1 LIVE REPORT -- generated {datetime.now():%Y-%m-%d %H:%M}",
           "\n_Single source of truth: research expectation vs forward shadow vs live "
           "execution. Verdicts: FAILS_FORWARD_EVIDENCE -> rejected; PASSES -> queued "
           "for post-window human review. This script promotes NOTHING to live._\n"]
    # research expectation: signals/day per stream from the persisted research streams
    exp = {}
    if os.path.exists(STREAMS):
        st = pd.read_csv(STREAMS, index_col=0, parse_dates=True)
        for c in st.columns:
            r = st[c].dropna()
            exp[c] = (r != 0).mean()          # share of days with activity (proxy rate)
    out.append("## Candidate: ETF universe expansion (9 survivors, forward shadow)")
    if sh.empty:
        out.append("_NO shadow data -- report cannot verdict; extend the window._")
    else:
        days = sh["date"].nunique()
        out.append(f"\n_{days} shadow days._\n")
        out.append("| stream | research act-rate/day | shadow rate/day | ratio | verdict |")
        out.append("|---|---|---|---|---|")
        per = sh.groupby("stream")["signal"].agg(["sum", "count"])
        for k, r in per.iterrows():
            e = exp.get(k)
            srate = r["sum"] / max(r["count"], 1)
            if e is None or days < 15:
                v = "EXTEND (insufficient days or no expectation)"
                ratio = ""
            else:
                ratio = f"{srate/max(e,1e-9):.2f}"
                v = ("PASSES -> post-window review queue" if srate >= 0.4 * e
                     else "FAILS_FORWARD_EVIDENCE -> rejected")
            out.append(f"| {k} | {'' if e is None else f'{e:.2f}'} | {srate:.2f} | {ratio} | {v} |")
    # ts-gate shadow
    if not sh.empty and "gate_ts_ratio" in sh:
        g = sh.drop_duplicates("date")[["date", "gate_vix_level", "gate_ts_ratio"]]
        agree = (g["gate_vix_level"].astype(float).gt(0) == g["gate_ts_ratio"].astype(float).gt(0)).mean()
        out.append(f"\n## Candidate: VIX term-structure gate (shadow)\n"
                   f"- {len(g)} gate-days logged; level-vs-ts agreement {agree:.0%}; "
                   f"ts blocked {int((g['gate_ts_ratio'].astype(float)==0).sum())} day(s), "
                   f"level blocked {int((g['gate_vix_level'].astype(float)==0).sum())}.")
        out.append("- Verdict: EXTEND unless a backwardation episode occurs in-window "
                   "(no stress episode = shadow cannot differentiate; do not promote on quiet data).")
    # live execution
    fl = read_fills()
    out.append("\n## Live execution vs research costs")
    if fl.empty:
        out.append("_No fills on this host. MT5 fills live on the VPS ledger -- merge "
                   "logs/fills.csv from the VPS before finalizing the go/no-go._")
    else:
        live = fl[fl.get("dry_run", "False").astype(str).str.lower() != "true"]
        s = pd.to_numeric(live.get("slippage_bps"), errors="coerce").dropna()
        out.append(f"- fills {len(live)} | slippage avg {s.mean():.1f} bps vs 3 bps model"
                   if len(s) else f"- fills {len(live)} | no slippage columns populated")
    out.append("\n## Decision inputs (human)\n- Ops ledger: docs/EVIDENCE_LEDGER.md\n"
               "- Parity/monitoring: NEXT_30_DAY_MONITORING_PLAN section 4 criteria\n"
               "- NOTHING here changes production; promotion requires human sign-off post-window.")
    p = os.path.join(REPO, "docs", "MONTH_1_LIVE_REPORT.md")
    open(p, "w").write("\n".join(out) + "\n")
    print(f"wrote docs/MONTH_1_LIVE_REPORT.md ({'no shadow data' if sh.empty else str(sh['date'].nunique())+' shadow days'})")




# ---- monthly evidence committee -------------------------------------------
# Validated research expectations, trades/day (source: FINDINGS/master lineage:
# S1~11/yr, S4~27/180d, S5~1.5 raw pre-filter -> ~0.8 taken, S2/S3 sparse,
# BTC occasional, OVN 2/wk by calendar). Used for expected-vs-actual only.
EXPECTED_PER_DAY = {"S1": 0.044, "S2": 0.063,  # daily-FVG lineage ported 07-12 (~16/yr); S2 clock starts 07-14
                    "S3": 0.03, "S4": 0.15,
                    "S5": 0.8, "SWEEP": 0.1, "BTC": 0.08, "OVN": 0.4, "BTCTREND": 0.05}
WINDOW_START = date(2026, 7, 9)          # parity commit 236abe3 -- clean-window anchor


def _trading_days_since(d0):
    n, d = 0, d0
    while d <= date.today():
        if d.weekday() < 5:
            n += 1
        d = d.fromordinal(d.toordinal() + 1)
    return max(n, 1)


def _live_trades_by_strategy():
    """Count real FILL lines per tag in this host's logs (+ fills.csv)."""
    import glob
    counts = {}
    for pth in glob.glob(os.path.join(REPO, "logs", "*.log")):
        for ln in open(pth, encoding="utf-8", errors="replace"):
            m = re.search(r"FILL (\w+) (BUY|SELL)", ln)
            if m and "DRY" not in ln and "WOULD" not in ln:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    fl = read_fills()
    if not fl.empty:
        live = fl[fl.get("dry_run", "False").astype(str).str.lower() != "true"]
        for k, n in live.groupby("strategy").size().items():
            counts[k] = max(counts.get(k, 0), int(n))
    return counts


def committee():
    days = _trading_days_since(WINDOW_START)
    sh = read_shadow()
    fl = read_fills()
    live_counts = _live_trades_by_strategy()
    shadow_days = sh["date"].nunique() if not sh.empty else 0

    # execution quality (host-local)
    slip = spread = "no data"
    if not fl.empty:
        lv = fl[fl.get("dry_run", "False").astype(str).str.lower() != "true"]
        s = pd.to_numeric(lv.get("slippage_bps"), errors="coerce").dropna()
        sp = pd.to_numeric(lv.get("spread_bps"), errors="coerce").dropna()
        if len(s):
            slip = f"{s.mean():.1f} bps avg / {s.max():.1f} worst (n={len(s)})"
        if len(sp):
            spread = f"{sp.mean():.1f} bps avg"

    out = [f"# MONTHLY EVIDENCE COMMITTEE REPORT -- {date.today().isoformat()}",
           f"\n_Clean window day {days} (anchor 2026-07-09 / parity 236abe3). Shadow days: "
           f"{shadow_days}. Host: local Mac -- MT5 fills live on the VPS ledger; cells that "
           f"need VPS data say so. NOTHING is promoted while the 30-day window runs "
           f"(clock rule) -- PROMOTE is structurally unavailable until the window closes._",
           "\n## Committee inputs",
           "1. Research backtests: validated lineage (master_backtest/full_yearly) + etf_streams.csv",
           "2. Forward shadow: research/results/shadow_signals.csv",
           "3. Live fills: logs/fills.csv + FILL log lines (this host)",
           f"4. Execution quality: slippage {slip} | spread {spread} | latency: not "
           "instrumented per-order; hourly polling bounds decision->submission at <=1h by design",
           "5. Parity: docs/LIVE_TRADING_PARITY.md (3 fixed bugs; open: one-entry-per-day, "
           "S3-on-MT5 exits, fill-timing approximation)",
           "\n## Per-strategy table (live book)",
           "| strategy | expected trades (window) | actual (this host) | missed | avg R | expectancy | Sharpe | maxDD | gates observed | live-vs-research notes | RECOMMENDATION |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]

    gate_note = "-"
    if not sh.empty:
        g = sh.drop_duplicates("date").iloc[-1]
        gate_note = f"lvl={g['gate_vix_level']} ts={g['gate_ts_ratio']}"

    for strat, epd in EXPECTED_PER_DAY.items():
        exp = epd * days
        act = live_counts.get(strat, 0)
        missed = "VPS data needed" if act == 0 else max(0, round(exp) - act)
        # R/expectancy/Sharpe/DD need closed trades -- none on this host yet
        stats = "insufficient closed trades"
        if exp >= 3 and act == 0:
            rec = "INVESTIGATE (expected>=3 in window, zero seen on this host -- check VPS logs/fills)"
        elif act > 0:
            rec = "CONTINUE SHADOW/LIVE-DEMO (accumulating)"
        else:
            rec = "CONTINUE (expected count in window still <3 -- sparsity, not silence)"
        parity = {"S3": "Alpaca-only exits (open blocker)",
                  "OVN": "time-exit + 5% cat-stop (intentional)",
                  "S5": "mid-bar entry approximation (measured via fills.csv)"}.get(strat, "parity clean")
        out.append(f"| {strat} | {exp:.1f} | {act} | {missed} | {stats} | - | - | - | "
                   f"{gate_note} | {parity} | {rec} |")

    out.append("\n## Shadow candidates")
    out.append("| candidate | research rate/day | shadow rate/day | shadow days | RECOMMENDATION |")
    out.append("|---|---|---|---|---|")
    if not sh.empty and os.path.exists(STREAMS):
        st = pd.read_csv(STREAMS, index_col=0, parse_dates=True)
        exp_rate = {c: (st[c].dropna() != 0).mean() for c in st.columns}
        per = sh.groupby("stream")["signal"].agg(["sum", "count"])
        for k, r in per.iterrows():
            e = exp_rate.get(k)
            srate = r["sum"] / max(r["count"], 1)
            if shadow_days >= 15 and e:
                rec = ("CONTINUE SHADOW -> post-window review" if srate >= 0.4 * e
                       else "REJECT (fails forward evidence)")
            else:
                rec = "CONTINUE SHADOW (insufficient days)"
            out.append(f"| {k} | {'' if e is None else f'{e:.2f}'} | {srate:.2f} | "
                       f"{int(r['count'])} | {rec} |")
    else:
        out.append("| (no shadow data) | | | | CONTINUE SHADOW |")
    out.append("| VIX term-structure gate | n/a (gate) | see ledger | "
               f"{shadow_days} | CONTINUE SHADOW (needs a backwardation episode to differentiate) |")

    out.append("\n## Committee rules applied")
    out.append("- PROMOTE: unavailable during the 30-day window, and additionally requires "
               "reviewer!=author sign-off + human decision (pipeline gates).")
    out.append("- REJECT: forward shadow < 40% of research rate with >=15 shadow days, "
               "or adversarial-review failure (see ATR compression precedent).")
    out.append("- INVESTIGATE: expected>=3 trades in the clean window with zero observed.")
    out.append("- CONTINUE SHADOW: everything else -- the honest default this early.")
    out.append("\n_Regenerate anytime: python scripts/ops/evidence_report.py --committee_")

    p_out = os.path.join(REPO, "docs", "MONTHLY_EVIDENCE_COMMITTEE.md")
    open(p_out, "w").write("\n".join(out) + "\n")
    print(f"wrote docs/MONTHLY_EVIDENCE_COMMITTEE.md (window day {days}, shadow days {shadow_days})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--daily", action="store_true")
    m.add_argument("--weekly", action="store_true")
    m.add_argument("--month-end", action="store_true")
    m.add_argument("--committee", action="store_true")
    a = ap.parse_args()
    (daily if a.daily else weekly if a.weekly else committee if a.committee else month_end)()
