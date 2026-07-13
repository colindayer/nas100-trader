"""NAS100 Trading OS -- decision cockpit (read-only view layer).

Never trades, never writes to production/research. Summarizes existing artifacts.
Run:  streamlit run dashboard/app.py   ->  http://localhost:8501
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import streamlit as st

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "ops"))
MONTH_END = date(2026, 8, 16)   # committee (reset from 08-11 by S2 fix 614e1ba)
WINDOW_START = date(2026, 7, 14)  # clock RESET by signal-touching S2 fix 614e1ba (was 07-09)

st.set_page_config(page_title="NAS100 Trading OS", page_icon="📈", layout="wide")
G, Y, R, DIM = "#22c55e", "#eab308", "#ef4444", "#8892a0"

# Bloomberg-ish: dark, dense, monospace numerics, amber accents
st.markdown("""<style>
.block-container{padding-top:1.2rem;max-width:1500px}
code,.mono{font-family:'SF Mono',Menlo,monospace}
[data-testid="stMetricValue"]{font-family:'SF Mono',Menlo,monospace}
.tick{font-family:'SF Mono',Menlo,monospace;font-size:.82em;padding:3px 10px;border-radius:4px;
 margin-right:6px;display:inline-block;background:#12161c;border:1px solid #232a33}
.card{border:1px solid #232a33;border-radius:8px;padding:10px 14px;margin:4px 0;background:#0e1217}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- loaders --
def md(rel):
    p = REPO / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def csv_rows(rel):
    p = REPO / rel
    if not p.exists() or p.stat().st_size == 0:
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def live_fills():
    return [r for r in csv_rows("logs/fills.csv")
            if str(r.get("dry_run", "")).lower() != "true"]


def tail(rel, n=800):
    p = REPO / rel
    return p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:] if p.exists() else []


def sh_git(*a):
    try:
        return subprocess.run(["git", *a], cwd=REPO, capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception as e:
        return f"(git: {e})"


def expected_per_day():
    try:
        import evidence_report as er
        return dict(er.EXPECTED_PER_DAY)
    except Exception:
        return {}


def kg():
    try:
        return json.loads(md("knowledge_graph.json"))
    except Exception:
        return {"nodes": [], "edges": []}


def ops_verdict():
    m = re.search(r"## VERDICT: \*\*([\w ]+)\*\*", md("docs/DAILY_OPS_REPORT.md"))
    return m.group(1) if m else "no report"


def trading_days(d0, d1):
    n, d = 0, d0
    while d <= d1:
        if d.weekday() < 5:
            n += 1
        d = date.fromordinal(d.toordinal() + 1)
    return max(n, 1)


def incidents():
    d = REPO / "vault" / "08-Incidents-and-Postmortems"
    return sorted((f.stem for f in d.glob("*.md") if f.stem[0].isdigit()), reverse=True) if d.is_dir() else []


def obsidian_button(label, rel):
    if (REPO / rel).exists():
        st.link_button(f"⧉ {label}", f"obsidian://open?path={quote(str(REPO / rel))}")


# ---- strategy self-explanation engine (rule-based, no AI) -----------------
STRAT = {  # mechanism + cadence unit; validation pulled from the knowledge graph
    "S1": ("Asian-low sweep + reclaim, VWAP/EMA50, GEX-gated", "weekly"),
    "S2": ("daily gold FVG gap-up + green + SPY-bull, long-only", "weekly"),
    "S3": ("daily abnormal volume + green, 5-day hold", "weekly"),
    "S4": ("dual-index sweep (QQQ+SPY) + EMA200 regime", "weekly"),
    "S5": ("opening-range breakout 10-13 ET, 1%/3:1", "daily"),
    "OVN": ("overnight drift close->open + 5% catastrophe stop", "daily"),
    "BTC": ("BTC sweep (S1 ported), 24/7", "weekly"),
    "BTCTREND": ("crypto trend/XSMOM daily rebalance (no broker stop)", "monthly"),
}


def kg_validation():
    return {n["id"]: n.get("validation", "?") for n in kg()["nodes"] if n["type"] == "strategy"}


# ---- static reconstruction tables (documentation of known logic, not strategy code) --
# entry gate chain each strategy requires, for plain-English "why the trade existed".
# Source: live_trader run_s* + STRATEGY_VALIDATION_AUDIT. Read-only reference.
GATES = {
    "S1": ["Asian-low swept then reclaimed", "in session window", "close > VWAP",
           "close > EMA50", "not high-vol regime", "GEX gate passed", "VIX gate passed"],
    "S2": ["daily FVG gap-up (low > high 2 days ago)", "green daily candle",
           "SPY bullish regime", "VIX gate passed"],
    "S3": ["abnormal volume (z-score/1.3x MA20)", "green close", "VIX gate passed"],
    "S4": ["QQQ+SPY dual sweep", "EMA200 regime aligned", "VIX gate passed"],
    "S5": ["opening-range breakout (close > 9:00 high)", "in 10-13 ET window",
           "volume > 0.6x ORB volume", "SPY bullish", "not QQQ-bear200", "VIX gate passed"],
    "OVN": ["overnight window", "calendar entry near close", "5% catastrophe stop set"],
    "BTC": ["BTC Asian sweep + reclaim (S1 ported)", "24/7 session", "reconcile guard clear"],
    "BTCTREND": ["daily trend/XSMOM rebalance signal", "no broker stop (rebalance-managed)"],
}
# expected research metrics per strategy: (trades/yr, Sharpe, win%, avgR, source)
EXPECTED = {
    "S5": (50, 0.88, 0.358, 0.432, "WEEKEND_EXPOSURE_AUDIT (A hold)"),
    "S1": (47, 0.23, 0.336, 0.342, "WEEKEND_EXPOSURE_AUDIT (A hold)"),
    "S3": (4, 0.06, 0.577, 0.109, "STRATEGY_VALIDATION_AUDIT (live subset)"),
    "S2": (16, 1.58, 0.560, None, "FINDINGS (daily-FVG replay)"),
    "S4": (55, None, None, None, "archetype of S1"),
    "OVN": (100, None, None, None, "OVERNIGHT_MOMENTUM_REVIEW"),
    "BTC": (15, None, None, None, "STRATEGY_VALIDATION_AUDIT (venue caveat)"),
    "BTCTREND": (12, None, None, None, "part_c_tsmom"),
}
OBS_NOTE = {"S1": "S1 Asian Sweep", "S2": "S2 Gold FVG", "S3": "S3 Abnormal Volume",
            "S4": "S4 Multi Sweep", "S5": "S5 ORB", "OVN": "Overnight Drift",
            "BTC": "BTC Sweep", "BTCTREND": "BTC Trend"}


def num(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def explain(strat):
    """Plain-English rule chain: why is this strategy quiet/active right now."""
    mech, unit = STRAT[strat]
    exp = expected_per_day().get(strat, 0.0)
    win = trading_days(WINDOW_START, date.today())
    fills = [r for r in live_fills() if r.get("strategy") == strat]
    val = kg_validation().get(strat, "?")
    per_wk = exp * 5
    expected_so_far = exp * win
    reasons = [f"mechanism: {mech}",
               f"expected rate: {exp:.3f}/day (~{per_wk:.2f}/week)",
               f"window fills (this host): {len(fills)} of ~{expected_so_far:.1f} expected so far",
               f"validation: {val}"]
    if val in ("PARTIAL", "PARTIAL-CFD"):
        status, why = "WATCH", "validation is PARTIAL -- see the audit; behavior is a safe subset / venue caveat"
    elif exp == 0:
        status, why = "NORMAL", "expected rate is 0 (no setups expected) -- silence is correct"
    elif len(fills) == 0 and expected_so_far >= 3:
        status, why = "INVESTIGATE", f"silent while ~{expected_so_far:.0f} were expected -- verify VPS fills, then parity"
    elif len(fills) == 0:
        status, why = "NORMAL", "no setups yet this window; below the expected-count threshold to flag"
    else:
        status, why = "ACTIVE", f"{len(fills)} fill(s) logged this window"
    return reasons, status, why


def badge(state):
    c = {"NORMAL": G, "ACTIVE": G, "GREEN": G, "WATCH": Y, "YELLOW": Y,
         "INVESTIGATE": R, "RED": R, "BLOCKED": R}.get(state, DIM)
    return f'<span style="color:{c};font-weight:700">{state}</span>'


# ---- shared header ticker (Bloomberg feel, every page) --------------------
def ticker():
    sh = csv_rows("research/results/shadow_signals.csv")
    sh_days = len({r["date"] for r in sh})
    today_fired = sum(int(r["signal"]) for r in sh if r["date"] == date.today().isoformat())
    win = trading_days(WINDOW_START, date.today())
    dleft = max((MONTH_END - date.today()).days, 0)
    ops = ops_verdict()
    items = [
        ("OPS", ops, G if ops == "HEALTHY" else (R if "ACTION" in ops else Y)),
        ("WINDOW", f"day {win}/30", G),
        ("LIVE FILLS", str(len(live_fills())), DIM),
        ("SHADOW", f"{sh_days}d ({today_fired} today)", G if sh_days else Y),
        ("COMMITTEE", f"{MONTH_END:%d %b} ({dleft}d)", Y),
        ("RESEARCH", "FROZEN", DIM),
        ("HEAD", sh_git("rev-parse", "--short", "HEAD"), DIM),
    ]
    st.markdown("".join(
        f'<span class="tick"><span style="color:{DIM}">{k}</span> '
        f'<span style="color:{c};font-weight:700">{v}</span></span>' for k, v, c in items),
        unsafe_allow_html=True)


# ------------------------------------------------------------------ pages --
PAGES = ["HOME", "STRATEGIES", "TRADE EXPLORER", "SHADOW", "RESEARCH", "GRAVEYARD",
         "EXECUTION", "EVIDENCE", "TIMELINE", "LOGS", "SETTINGS"]
page = st.sidebar.radio("Cockpit", PAGES)
auto = st.sidebar.toggle("Auto-refresh 60 s", value=True)
if auto:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
st.sidebar.caption("Read-only. Never trades. Never writes.")
st.sidebar.divider()
obsidian_button("Knowledge Graph", "docs/KNOWLEDGE_GRAPH.md")
obsidian_button("Data Lineage", "docs/DATA_LINEAGE.md")

ticker()
st.divider()

if page == "HOME":
    st.subheader("NAS100 Trading OS — the glance")
    win = trading_days(WINDOW_START, date.today())
    sh = csv_rows("research/results/shadow_signals.csv")
    sh_days = len({r["date"] for r in sh})
    c1, c2, c3 = st.columns(3)
    # WHAT'S TRADING / FIRED
    with c1:
        st.markdown("**What is trading?**")
        for s in STRAT:
            _, statv, _ = explain(s)
            st.markdown(f'`{s:9}` {badge(statv)}', unsafe_allow_html=True)
    # WHAT'S BROKEN / WAITING
    with c2:
        st.markdown("**What's broken / waiting?**")
        ops = ops_verdict()
        st.markdown(f"- ops: {badge('GREEN' if ops=='HEALTHY' else 'RED' if 'ACTION' in ops else 'YELLOW')}", unsafe_allow_html=True)
        bl = re.search(r"SHADOW (\d+) \| WAITING (\d+)", md("docs/RESEARCH_BACKLOG.md"))
        if bl:
            st.markdown(f"- research: {bl[1]} shadow, {bl[2]} waiting (frozen)")
        st.markdown("- VPS/MT5: authoritative on `status.py` (VPS)")
        st.markdown(f"- last incident: `{incidents()[0] if incidents() else 'none'}`")
    # NEXT DECISION / HOW CLOSE
    with c3:
        st.markdown("**Next decision / how close?**")
        dleft = max((MONTH_END - date.today()).days, 0)
        st.markdown(f'<div class="card"><b>Month 1 Committee</b><br>{MONTH_END:%d %b %Y} — '
                    f'<span style="color:{Y}">{dleft} days</span></div>', unsafe_allow_html=True)
        st.progress(min(win / 30, 1.0), text=f"evidence {win}/30 trading days")
        lf = live_fills()
        for label, frac in [("shadow evidence", min(sh_days / 15, 1.0)),
                            ("execution measured", 1.0 if lf else 0.0)]:
            st.progress(frac, text=label)
    st.divider()
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("**Latest fired (shadow, today)**")
        fired = [r for r in sh if r.get("signal") == "1"][-6:]
        st.table(fired or [{"info": "none fired yet"}])
    with f2:
        st.markdown("**Latest fills (live)**")
        st.table(live_fills()[-6:] or [{"info": "No live fills yet"}])
    with f3:
        st.markdown("**Latest audit / research**")
        for label, rel in [("Validation Audit", "docs/STRATEGY_VALIDATION_AUDIT.md"),
                           ("Weekend Audit", "docs/WEEKEND_EXPOSURE_AUDIT.md"),
                           ("Research Backlog", "docs/RESEARCH_BACKLOG.md"),
                           ("Knowledge Graph", "docs/KNOWLEDGE_GRAPH.md")]:
            st.markdown(f"- [{label}]({rel})")

elif page == "STRATEGIES":
    st.subheader("Strategy cards — each explains itself")
    val = kg_validation()
    for s, (mech, unit) in STRAT.items():
        reasons, statv, why = explain(s)
        with st.container(border=True):
            a, b = st.columns([1, 3])
            a.markdown(f"### {s}")
            a.markdown(badge(statv), unsafe_allow_html=True)
            a.caption(f"validation: {val.get(s,'?')}")
            b.markdown(f"**Why {statv.lower()}?** {why}")
            with b.expander("reasoning chain"):
                for r in reasons:
                    st.markdown(f"- {r}")
            obs = {"S1": "S1 Asian Sweep", "S2": "S2 Gold FVG", "S3": "S3 Abnormal Volume",
                   "S4": "S4 Multi Sweep", "S5": "S5 ORB", "OVN": "Overnight Drift",
                   "BTC": "BTC Sweep", "BTCTREND": "BTC Trend"}.get(s)
            if obs:
                with b:
                    obsidian_button(f"{s} note", f"vault/03-Validated-Strategies/{obs}.md")
    st.caption("Status is rule-derived from expected rate x window days vs logged fills + "
               "knowledge-graph validation. No AI. See docs/KNOWLEDGE_GRAPH.md.")

elif page == "TRADE EXPLORER":
    st.subheader("Trade Explorer — investigate any trade in <30s")
    all_rows = csv_rows("logs/fills.csv")
    if not all_rows:
        st.info("**No trades in the ledger yet.** logs/fills.csv is empty — the "
                "explorer lights up automatically as the system logs fills (real on "
                "the VPS; dry-run rows appear here too). Everything below is ready.")
    else:
        # -------- SEARCH / filters --------
        with st.container(border=True):
            c = st.columns(4)
            strat = c[0].selectbox("strategy", ["(any)"] + sorted({r.get("strategy", "") for r in all_rows}))
            sym = c[1].selectbox("symbol", ["(any)"] + sorted({r.get("symbol", "") for r in all_rows}))
            outcome = c[2].selectbox("outcome", ["(any)", "winner", "loser", "open"])
            tag = c[3].selectbox("tag", ["(any)", "weekend hold", "overnight", "partial-validation", "dry-run", "real"])
            q = st.text_input("free search (date / symbol / order id)", "")

        def achieved_r(r):
            """R from the row if a stop is known; entry-only rows -> None (bracket
            closes are broker-side; blocker #3). Read-only derivation."""
            try:
                fp, sp = float(r["fill_price"]), float(r["stop_price"])
                exitp = r.get("exit_price") or r.get("close_price")
                if exitp and fp != sp:
                    return (float(exitp) - fp) / abs(fp - sp) * (1 if r.get("side") == "buy" else -1)
            except (TypeError, ValueError, KeyError):
                pass
            return None

        def is_weekend(r):
            try:
                return pd.Timestamp(r["timestamp_utc"]).weekday() == 4
            except Exception:
                return False

        import pandas as pd
        rows = all_rows
        if strat != "(any)":
            rows = [r for r in rows if r.get("strategy") == strat]
        if sym != "(any)":
            rows = [r for r in rows if r.get("symbol") == sym]
        if outcome != "(any)":
            def oc(r):
                ar = achieved_r(r)
                return "open" if ar is None else ("winner" if ar > 0 else "loser")
            rows = [r for r in rows if oc(r) == outcome]
        if tag == "weekend hold":
            rows = [r for r in rows if is_weekend(r)]
        elif tag == "overnight":
            rows = [r for r in rows if r.get("strategy") == "OVN"]
        elif tag == "partial-validation":
            pv = {k for k, v in kg_validation().items() if v.startswith("PARTIAL")}
            rows = [r for r in rows if r.get("strategy") in pv]
        elif tag == "dry-run":
            rows = [r for r in rows if str(r.get("dry_run", "")).lower() == "true"]
        elif tag == "real":
            rows = [r for r in rows if str(r.get("dry_run", "")).lower() != "true"]
        if q:
            rows = [r for r in rows if any(q.lower() in str(v).lower() for v in r.values())]

        st.caption(f"{len(rows)} of {len(all_rows)} trades match")
        if not rows:
            st.warning("No trades match the filters.")
        else:
            labels = [f"{i}: {r.get('timestamp_utc','?')[:16]} {r.get('strategy','?')} "
                      f"{r.get('symbol','?')} {r.get('side','?')}" for i, r in enumerate(rows)]
            pick = st.selectbox("select a trade", range(len(rows)), format_func=lambda i: labels[i])
            r = rows[pick]
            s = r.get("strategy", "")
            ar = achieved_r(r)
            status = "OPEN" if ar is None else ("WIN" if ar > 0 else "LOSS")

            # -------- HEADER --------
            h = st.columns(6)
            h[0].metric("strategy", s); h[1].metric("ticker", r.get("symbol", "—"))
            h[2].metric("direction", r.get("side", "—")); h[3].markdown(f"**status**\n\n{badge(status if status!='LOSS' else 'INVESTIGATE')}", unsafe_allow_html=True)
            h[4].metric("risk %", num(float(r["risk_scale"]) * 0.7, 2) + "%" if r.get("risk_scale") else "—")
            h[5].metric("R", num(ar) if ar is not None else "open")
            st.caption(f"entry {r.get('timestamp_utc','—')} · signal {r.get('signal_timestamp','—')} · "
                       f"exit {r.get('exit_price') and r.get('timestamp_utc') or 'in ledger: not recorded (bracket closes are broker-side)'}")

            colA, colB = st.columns(2)
            # -------- WHY THE TRADE EXISTED --------
            with colA:
                st.markdown("**Why the trade existed** (rule reconstruction)")
                for g in GATES.get(s, ["(no gate chain on file for this strategy)"]):
                    st.markdown(f"- {g}")
                if r.get("risk_scale"):
                    st.markdown(f"- risk throttle: {r['risk_scale']}")
                st.caption("Reconstructed from live_trader gate chain + this fill's logged "
                           "context. No AI. Confirm against the raw log (button below).")
            # -------- RESEARCH CONTEXT --------
            with colB:
                st.markdown("**Research context**")
                val = kg_validation().get(s, "?")
                fr, sh, wn, avgr, src = EXPECTED.get(s, (None,)*5)
                st.markdown(f"- validated strategy? **{val}**")
                st.markdown(f"- expected freq: **{fr or '—'}/yr** · Sharpe **{sh or '—'}** · "
                            f"win **{f'{wn:.0%}' if wn else '—'}** ({src})")
                pv = "live rule = strict subset" if s == "S3" else (
                     "CFD opening-range premise weak" if s == "S5" else (
                     "venue swap (Binance→CFD)" if s == "BTC" else "none"))
                st.markdown(f"- known validation issues: {pv}")
                st.markdown(f"- committee notes: decision deferred to {MONTH_END:%d %b} "
                            f"(see MONTHLY_EVIDENCE_COMMITTEE)")

            # -------- EXECUTION --------
            st.markdown("**Execution**")
            e = st.columns(6)
            e[0].metric("entry/fill", num(r.get("fill_price"), 5))
            e[1].metric("stop", num(r.get("stop_price"), 5))
            e[2].metric("target", num(r.get("target_price"), 5))
            e[3].metric("slippage bps", num(r.get("slippage_bps")))
            e[4].metric("spread bps", num(r.get("spread_bps")))
            e[5].metric("broker sym", r.get("symbol", "—"))
            st.caption(f"broker: {r.get('broker','—')} · account: {r.get('account','—')} · "
                       f"commission/swap: not in ledger (broker-side; export MT5 history) · "
                       f"weekend hold: {'YES' if is_weekend(r) else 'no'} · "
                       f"overnight financing: {'~3bps/day (CFD)' if r.get('broker')=='mt5' else 'n/a (ETF)'}")

            # -------- CHART --------
            st.markdown("**Chart**")
            csv_name = f"{r.get('symbol','').lower()}_hourly_7y.csv"
            plotted = False
            if (REPO / csv_name).exists() and r.get("timestamp_utc"):
                try:
                    d = pd.read_csv(REPO / csv_name)
                    tcol = "timestamp" if "timestamp" in d.columns else d.columns[0]
                    d[tcol] = pd.to_datetime(d[tcol], utc=True, errors="coerce")
                    t0 = pd.Timestamp(r["timestamp_utc"], tz="UTC")
                    win = d[(d[tcol] >= t0 - pd.Timedelta(days=3)) & (d[tcol] <= t0 + pd.Timedelta(days=3))]
                    if len(win):
                        cc = "close" if "close" in win.columns else win.columns[-2]
                        st.line_chart(win.set_index(tcol)[cc]); plotted = True
                except Exception:
                    pass
            if not plotted:
                st.info("No chart available (no covering candle history for this window).")

            # -------- TIMELINE --------
            st.markdown("**Timeline** (decisions from logs around this fill)")
            key = f"{s}|{r.get('symbol','')}"
            day = (r.get("timestamp_utc") or "")[:10]
            hits = [l for l in tail("logs/trader.log", 2000)
                    if day and day in l and (s in l or r.get("symbol", "") in l)][:25]
            st.code("\n".join(hits) or "(no matching log lines on this host — VPS logs hold MT5 session detail)")

            # -------- DIAGNOSTICS --------
            st.markdown("**Diagnostics**")
            fr, sh, wn, exp_r, _ = EXPECTED.get(s, (None, None, None, None, None))
            dg = st.columns(4)
            dg[0].metric("research exp R", num(exp_r) if exp_r else "—")
            dg[1].metric("live achieved R", num(ar) if ar is not None else "open")
            dg[2].metric("R difference", num(ar - exp_r) if (ar is not None and exp_r) else "—")
            dg[3].metric("validation", kg_validation().get(s, "?"))
            st.caption(f"research version: master_backtest/full_yearly lineage · production: "
                       f"live_trader run_{s.lower() if s.startswith('S') else s} · "
                       f"parity: see LIVE_TRADING_PARITY · hold time: "
                       f"{'exit not in ledger' if ar is None else 'from fill pair'}")

            # -------- BONUS --------
            b = st.columns(3)
            with b[0]:
                if OBS_NOTE.get(s):
                    obsidian_button("related Obsidian note", f"vault/03-Validated-Strategies/{OBS_NOTE[s]}.md")
            with b[1]:
                obsidian_button("research review", "docs/STRATEGY_VALIDATION_AUDIT.md")
            with b[2]:
                obsidian_button("raw log", "logs/trader.log")

elif page == "TIMELINE":
    st.subheader("Timeline — window, resets, incidents, commits")
    ev = []
    ev.append((str(WINDOW_START), "🟢 clean evidence window START (anchor)"))
    ev.append((str(MONTH_END), "🏛️ Month 1 committee (go/no-go)"))
    for line in md("docs/CLOCK_RESETS.md").splitlines():
        m = re.search(r"Reset \d+ -- (\d{4}-\d{2}-\d{2})", line)
        if m:
            ev.append((m[1], "🔴 clock RESET (signal-touching change)"))
    for i in incidents()[:6]:
        ev.append((i[:10], f"⚠️ incident: {i}"))
    for line in sh_git("log", "-12", "--format=%cd|%h|%s", "--date=short").splitlines():
        try:
            d, h, s = line.split("|", 2)
            ev.append((d, f"`{h}` {s[:70]}"))
        except ValueError:
            pass
    for d, label in sorted(ev, reverse=True):
        st.markdown(f"`{d}`  {label}")

elif page == "SHADOW":
    st.subheader("Forward shadow — research vs actual")
    sh = csv_rows("research/results/shadow_signals.csv")
    days = len({r["date"] for r in sh})
    st.progress(min(days / 15, 1.0), text=f"{days}/15 days to pre-registered verdict")
    rev = md("docs/ETF_FORWARD_SHADOW_REVIEW.md")
    exp = dict(re.findall(r"\| (S\d_\w+) \| \d+ \| \d+ \| ([\d.]+) \|", rev))
    if sh:
        per = {}
        for r in sh:
            per.setdefault(r["stream"], [0, 0])
            per[r["stream"]][1] += 1
            per[r["stream"]][0] += int(r["signal"])
        rows = "| stream | research exp/day | shadow/day | diff | conf | status |\n|---|---|---|---|---|---|\n"
        for k, (f_, n) in sorted(per.items()):
            e = float(exp.get(k, 0) or 0)
            a = f_ / max(n, 1)
            conf = "LOW" if n < 15 else ("HIGH" if n >= 30 else "MED")
            stat = "🟢" if abs(a - e) <= max(0.6 * e, 0.1) else ("🟡" if a > e else "🔴")
            rows += f"| {k} | {e:.2f} | {a:.2f} | {a-e:+.2f} | {conf} | {stat} |\n"
        st.markdown(rows)
    else:
        st.info("No shadow data yet.")

elif page == "RESEARCH":
    st.subheader("Research pipeline (frozen)")
    counts = {k: len(list((REPO / p).glob(g))) if (REPO / p).exists() else 0
              for k, (p, g) in {"Papers": ("research/papers", "*.md"),
                                "Ideas": ("research/ideas", "*.md"),
                                "Queue": ("research/queue", "EXP-*.md"),
                                "Active": ("research/experiments", "EXP-*.md"),
                                "Archive": ("research/archive", "EXP-*.md")}.items()}
    st.markdown(" → ".join(f"**{k}** ({v})" for k, v in counts.items()) + " → Production (frozen) → Graveyard")
    st.markdown(md("docs/RESEARCH_BACKLOG.md") or "_missing_")
    notes = sorted(str(p.relative_to(REPO)) for pat in
                   ("research/ideas/*.md", "research/archive/*.md", "research/results/*.md")
                   for p in REPO.glob(pat))
    if notes:
        sel = st.selectbox("open a note", notes)
        obsidian_button(Path(sel).stem, sel)
        st.markdown(md(sel))

elif page == "GRAVEYARD":
    st.subheader("Graveyard (searchable)")
    txt = md("docs/RESEARCH_GRAVEYARD_AUDIT.md")
    q = st.text_input("search", "")
    rowsg = re.findall(r"^\| \d+ \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$", txt, re.M)
    shown = [r for r in rowsg if not q or q.lower() in " ".join(r).lower()]
    st.caption(f"{len(shown)}/{len(rowsg)} entries")
    for idea, reason, ev, when in shown:
        st.markdown(f'<div class="card"><b>{idea}</b><br>reason: {reason}<br>'
                    f'evidence: {ev} · since: {when}</div>', unsafe_allow_html=True)

elif page == "EXECUTION":
    st.subheader("Execution quality")
    lf = live_fills()
    if not lf:
        st.info("No live fills yet. (MT5 fills land on the VPS ledger.)")
    else:
        import pandas as pd
        df = pd.DataFrame(lf)
        for c in ("slippage_bps", "spread_bps", "account_equity"):
            df[c] = pd.to_numeric(df.get(c), errors="coerce")
        df["ts"] = pd.to_datetime(df["timestamp_utc"], errors="coerce")
        eq = df.dropna(subset=["account_equity"]).set_index("ts")["account_equity"]
        if len(eq):
            st.line_chart(eq); st.area_chart(eq / eq.cummax() - 1)
        st.bar_chart(df.dropna(subset=["slippage_bps"]).set_index("ts")["slippage_bps"])
        st.dataframe(df.tail(30), use_container_width=True)

elif page == "EVIDENCE":
    st.subheader("Evidence")
    tabs = st.tabs(["COMMITTEE", "READINESS", "LEDGER", "VALIDATION AUDIT",
                    "WEEKEND AUDIT", "KNOWLEDGE GRAPH"])
    for tab, rel in zip(tabs, ["docs/MONTHLY_EVIDENCE_COMMITTEE.md", "docs/PROP_READINESS.md",
                               "docs/EVIDENCE_LEDGER.md", "docs/STRATEGY_VALIDATION_AUDIT.md",
                               "docs/WEEKEND_EXPOSURE_AUDIT.md", "docs/KNOWLEDGE_GRAPH.md"]):
        with tab:
            st.markdown(md(rel) or f"_{rel} missing_")

elif page == "LOGS":
    st.subheader("Logs")
    logs = sorted(str(p.relative_to(REPO)) for p in (REPO / "logs").glob("*.log")) \
        if (REPO / "logs").exists() else []
    if not logs:
        st.info("no log files")
    else:
        sel = st.selectbox("file", logs, index=logs.index("logs/trader.log")
                           if "logs/trader.log" in logs else 0)
        q = st.text_input("filter", "")
        only_err = st.checkbox("errors only")
        lines = tail(sel)
        if only_err:
            lines = [l for l in lines if re.search(r"CRASH|FAIL|ERROR|ALERT|NAKED", l)]
        if q:
            lines = [l for l in lines if q in l]
        st.code("\n".join(lines[-400:]) or "(no matches)")

elif page == "SETTINGS":
    st.subheader("Settings / environment")
    fresh = {rel: (datetime.fromtimestamp((REPO / rel).stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                   if (REPO / rel).exists() else "missing")
             for rel in ["docs/EVIDENCE_LEDGER.md", "research/results/shadow_signals.csv",
                         "logs/fills.csv", "knowledge_graph.json"]}
    st.write({"repository": str(REPO), "commit": sh_git("rev-parse", "--short", "HEAD"),
              "branch": sh_git("branch", "--show-current"),
              "last sync": sh_git("log", "-1", "--format=%ci %s"),
              "window": f"{WINDOW_START} -> committee {MONTH_END}", "data freshness": fresh})
    st.caption("VPS status: run `python status.py` on the VPS (authoritative).")
