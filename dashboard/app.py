"""NAS100 Trading OS -- decision cockpit (read-only view layer).

Never trades, never writes to production/research. Summarizes existing artifacts.
Run:  streamlit run dashboard/app.py   ->  http://localhost:8501
"""
from __future__ import annotations

import csv
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

G, Y, R = "#22c55e", "#eab308", "#ef4444"


# ---------------------------------------------------------------- loaders --
def md(rel):  # noqa: ANN001
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


def card(col, title, state, detail=""):
    c = {"GREEN": G, "YELLOW": Y, "RED": R}.get(state, "#666")
    col.markdown(
        f'<div style="border:1px solid {c};border-left:8px solid {c};'
        f'border-radius:10px;padding:10px 14px;margin:4px 0;">'
        f'<div style="font-size:0.8em;opacity:.7">{title}</div>'
        f'<div style="font-size:1.15em;font-weight:700;color:{c}">{state}</div>'
        f'<div style="font-size:0.75em;opacity:.6">{detail}</div></div>',
        unsafe_allow_html=True)


def obsidian_button(label, rel):
    p = (REPO / rel)
    if p.exists():
        st.link_button(f"Open in Obsidian: {label}",
                       f"obsidian://open?path={quote(str(p))}")


def commander():
    """Derive recommendations ONLY from existing artifacts. Max 3."""
    recs = []
    sh = csv_rows("research/results/shadow_signals.csv")
    sh_days = len({r["date"] for r in sh})
    win_days = trading_days(WINDOW_START, date.today())
    exp = expected_per_day()
    if "ACTION" in ops_verdict():
        recs.append(("RED", "Ops verdict is ACTION REQUIRED -- triage docs/DAILY_OPS_REPORT.md."))
    if f"| {date.today().isoformat()} |" not in md("docs/EVIDENCE_LEDGER.md"):
        recs.append(("YELLOW", "Today's evidence ledger line missing -- run the daily trio."))
    # S5 silence rule (derived: expectation x window days vs live fills on this host)
    s5_expected = exp.get("S5", 0) * win_days
    s5_fills = sum(1 for r in live_fills() if r.get("strategy") == "S5")
    if s5_expected >= 5 and s5_fills == 0:
        recs.append(("YELLOW", f"S5 expected ~{s5_expected:.0f} trades in window, 0 fills "
                               f"on this host -- verify VPS fills, then investigate parity."))
    if sh_days >= 15:
        recs.append(("GREEN", f"ETF shadow reached {sh_days} days -- queue committee review."))
    if not recs:
        recs.append(("GREEN", "Nothing required today. System healthy. Continue evidence month."))
    return recs[:3], sh_days, win_days


# ------------------------------------------------------------------ pages --
PAGES = ["HOME", "STRATEGIES", "SHADOW", "RESEARCH", "GRAVEYARD",
         "EXECUTION", "EVIDENCE", "LOGS", "SETTINGS"]
page = st.sidebar.radio("Cockpit", PAGES)
auto = st.sidebar.toggle("Auto-refresh 60 s", value=True)
if auto:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
st.sidebar.caption("Read-only. Never trades. Never writes.")

if page == "HOME":
    st.title("NAS100 Trading OS -- Command Center")
    recs, sh_days, win_days = commander()

    # SYSTEM STATUS cards
    ops = ops_verdict()
    cols = st.columns(6)
    card(cols[0], "System Health", "GREEN" if ops == "HEALTHY" else
         ("RED" if "ACTION" in ops else "YELLOW"), f"ops: {ops}")
    card(cols[1], "VPS", "YELLOW", "not visible from host -- status.py on VPS")
    card(cols[2], "MT5", "YELLOW", "see VPS status.py")
    card(cols[3], "Scheduler", "GREEN" if f"| {date.today().isoformat()} |" in
         md("docs/EVIDENCE_LEDGER.md") else "YELLOW", "ledger heartbeat")
    card(cols[4], "Research", "GREEN", "FROZEN (by design)")
    card(cols[5], "Shadow", "GREEN" if sh_days else "YELLOW", f"{sh_days} day(s)")

    st.divider()
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("AI COMMANDER")
        for state, txt in recs:
            c = {"GREEN": G, "YELLOW": Y, "RED": R}[state]
            st.markdown(f'<div style="border-left:6px solid {c};padding:6px 12px;'
                        f'margin:6px 0;background:rgba(255,255,255,.03)">{txt}</div>',
                        unsafe_allow_html=True)
        st.subheader("TODAY")
        for _, txt in recs:
            st.markdown(f"- {txt}")
        st.subheader("EVIDENCE MONTH")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Window day", f"{win_days} / 30")
        m2.metric("Shadow days", sh_days)
        m3.metric("Live fills (host)", len(live_fills()))
        m4.metric("Committee", MONTH_END.strftime("%d %b"))
        st.progress(min(win_days / 30, 1.0))
    with right:
        st.subheader("NEXT DECISION")
        days_left = max((MONTH_END - date.today()).days, 0)
        st.markdown(f'<div style="border:2px solid {G};border-radius:12px;padding:18px;'
                    f'text-align:center"><div style="font-size:1.6em;font-weight:800">'
                    f'Month 1 Committee</div><div style="font-size:1.2em">'
                    f'{MONTH_END.strftime("%d %b %Y")} -- in {days_left} days</div></div>',
                    unsafe_allow_html=True)
        st.subheader("LIVE BOOK")
        lf = live_fills()
        led = [l for l in md("docs/EVIDENCE_LEDGER.md").splitlines()
               if l.startswith("| 20")]
        st.write({"equity / DD / risk scale": "Available on VPS (status.py)",
                  "open positions": "Available on VPS",
                  "today's PnL": "Available on VPS",
                  "last fill (host)": lf[-1]["timestamp_utc"] if lf else "none yet",
                  "last ledger line": led[-1] if led else "none"})
        st.subheader("PROP READINESS")
        for label, frac in [("Design ready", 1.0),
                            ("Evidence progress", min(win_days / 30, 1.0)),
                            ("Execution quality (fills measured)", 1.0 if lf else 0.0),
                            ("Shadow evidence", min(sh_days / 15, 1.0)),
                            ("Operational stability (window clean)", min(win_days / 30, 1.0))]:
            st.progress(frac, text=label)
    st.divider()
    st.subheader("ALERTS (newest first)")
    alerts = [l for l in tail("logs/trader.log")
              if re.search(r"CRASH|FAIL|ERROR|NAKED|WATCHDOG", l)][-10:][::-1]
    st.code("\n".join(alerts) or "no warnings/errors in recent log")

elif page == "STRATEGIES":
    st.title("Strategy cards")
    sh = csv_rows("research/results/shadow_signals.csv")
    exp = expected_per_day()
    audit = md("docs/STRATEGY_VALIDATION_AUDIT.md")
    fills = live_fills()
    META = {  # status/issues sourced from the validation audit + backlog docs
        "S1": ("LIVE", "validation YES (post-parity)"),
        "S2": ("LIVE (clock restarted 07-14)", "ported to validated daily-FVG lineage 07-12"),
        "S3": ("LIVE -- PARTIAL validation", "provenance drift: live rule = strict subset (~4/yr vs 15/yr) -- post-window decision"),
        "S4": ("LIVE", "validation YES (post-parity)"),
        "S5": ("LIVE", "PARTIAL on CFD (9:00 bar is not an auction open on NAS100) -- measured via fills"),
        "OVN": ("LIVE", "validation YES; 5% catastrophe stop additive"),
        "BTC": ("LIVE", "PARTIAL: Binance-validated, CFD-traded -- month-end comparison"),
        "BTCTREND": ("LIVE (yellow risk)", "rebalance-managed, no broker stop -- keep off funded"),
    }
    for strat, (status, issue) in META.items():
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 2, 1])
            c1.markdown(f"### {strat}")
            c1.caption(status)
            last_fill = next((r["timestamp_utc"] for r in reversed(fills)
                              if r.get("strategy") == strat), "none")
            sh_rate = ""
            srows = [r for r in sh if r["stream"].startswith(strat + "_")]
            if srows:
                sh_rate = f"{sum(int(r['signal']) for r in srows)}/{len(srows)} shadow rows fired"
            c2.write({"expected trades/day": exp.get(strat, "n/a"),
                      "last fill (host)": last_fill,
                      "shadow": sh_rate or "not shadowed (live strategy)",
                      "gate status": "see daily ledger (lvl/ts columns)",
                      "open issues": issue})
            with c3:
                obsidian_button("validation audit", "docs/STRATEGY_VALIDATION_AUDIT.md")
                obsidian_button("parity", "docs/LIVE_TRADING_PARITY.md")

elif page == "SHADOW":
    st.title("Forward shadow -- research vs actual")
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
        st.markdown("| stream | research exp/day | shadow actual/day | diff | confidence | status |")
        st.markdown("|---|---|---|---|---|---|")
        rows_md = []
        for k, (f_, n) in sorted(per.items()):
            e = float(exp.get(k, 0) or 0)
            a = f_ / max(n, 1)
            diff = a - e
            conf = "LOW" if n < 15 else ("HIGH" if n >= 30 else "MED")
            stat = "🟢 on-model" if abs(diff) <= max(0.6 * e, 0.1) else \
                   ("🟡 hot" if diff > 0 else "🔴 cold")
            rows_md.append(f"| {k} | {e:.2f} | {a:.2f} | {diff:+.2f} | {conf} | {stat} |")
        st.markdown("\n".join(rows_md))
    else:
        st.info("No shadow data yet.")

elif page == "RESEARCH":
    st.title("Research pipeline")
    counts = {
        "Papers": len(list((REPO / "research/papers").glob("*.md"))) if (REPO / "research/papers").exists() else 0,
        "Ideas": len(list((REPO / "research/ideas").glob("*.md"))) if (REPO / "research/ideas").exists() else 0,
        "Queue": len(list((REPO / "research/queue").glob("EXP-*.md"))) if (REPO / "research/queue").exists() else 0,
        "Active": len(list((REPO / "research/experiments").glob("EXP-*.md"))) if (REPO / "research/experiments").exists() else 0,
        "Archive (done)": len(list((REPO / "research/archive").glob("EXP-*.md"))) if (REPO / "research/archive").exists() else 0,
    }
    st.markdown(" → ".join(f"**{k}** ({v})" for k, v in counts.items())
                + " → **Production** (frozen) → **Graveyard** (see page)")
    st.divider()
    st.subheader("Backlog (from RESEARCH_BACKLOG.md)")
    txt = md("docs/RESEARCH_BACKLOG.md")
    m = re.search(r"SHADOW (\d+) \| WAITING (\d+) \| REJECTED (\d+) \| ARCHIVED (\d+) \| READY (\d+)", txt)
    if m:
        c = st.columns(5)
        for col, (label, val) in zip(c, [("READY", m[5]), ("SHADOW", m[1]),
                                         ("WAITING", m[2]), ("ARCHIVED", m[4]),
                                         ("REJECTED", m[3])]):
            col.metric(label, val)
    st.markdown(txt or "_missing_")
    st.subheader("Open any research note")
    notes = sorted(str(p.relative_to(REPO)) for pat in
                   ("research/ideas/*.md", "research/papers/*.md",
                    "research/archive/*.md", "research/results/*.md")
                   for p in REPO.glob(pat))
    if notes:
        sel = st.selectbox("note", notes)
        obsidian_button(Path(sel).stem, sel)
        st.markdown(md(sel))

elif page == "GRAVEYARD":
    st.title("Graveyard (searchable)")
    txt = md("docs/RESEARCH_GRAVEYARD_AUDIT.md")
    q = st.text_input("search rejected ideas", "")
    rows_g = re.findall(r"^\| \d+ \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$", txt, re.M)
    shown = [r for r in rows_g if not q or q.lower() in " ".join(r).lower()]
    st.caption(f"{len(shown)}/{len(rows_g)} entries")
    for idea, reason, evidence, new in shown:
        with st.container(border=True):
            st.markdown(f"**{idea}**  \nreason: {reason}  \nevidence: {evidence}  \nsince: {new}")
    obsidian_button("full graveyard audit", "docs/RESEARCH_GRAVEYARD_AUDIT.md")
    obsidian_button("FINDINGS (raw log)", "FINDINGS.md")

elif page == "EXECUTION":
    st.title("Execution quality")
    lf = live_fills()
    if not lf:
        st.info("No live fills yet. (MT5 fills land on the VPS ledger.)")
    else:
        import pandas as pd
        df = pd.DataFrame(lf)
        for col in ("slippage_bps", "spread_bps", "account_equity"):
            df[col] = pd.to_numeric(df.get(col), errors="coerce")
        df["ts"] = pd.to_datetime(df["timestamp_utc"], errors="coerce")
        eq = df.dropna(subset=["account_equity"]).set_index("ts")["account_equity"]
        if len(eq):
            st.subheader("Equity")
            st.line_chart(eq)
            st.subheader("Drawdown")
            st.area_chart(eq / eq.cummax() - 1)
        st.subheader("Slippage (bps)")
        st.bar_chart(df.dropna(subset=["slippage_bps"]).set_index("ts")["slippage_bps"])
        st.subheader("Spread (bps)")
        st.bar_chart(df.dropna(subset=["spread_bps"]).set_index("ts")["spread_bps"])
        st.subheader("Fills per day")
        st.bar_chart(df.groupby(df["ts"].dt.date).size())
        st.subheader("Recent fills")
        st.dataframe(df.tail(30), use_container_width=True)

elif page == "EVIDENCE":
    st.title("Evidence")
    tabs = st.tabs(["COMMAND CENTER", "COMMITTEE", "READINESS", "LEDGER",
                    "VALIDATION AUDIT"])
    for tab, rel in zip(tabs, ["dashboard/COMMAND_CENTER.md",
                               "docs/MONTHLY_EVIDENCE_COMMITTEE.md",
                               "docs/PROP_READINESS.md", "docs/EVIDENCE_LEDGER.md",
                               "docs/STRATEGY_VALIDATION_AUDIT.md"]):
        with tab:
            st.markdown(md(rel) or f"_{rel} missing_")

elif page == "LOGS":
    st.title("Logs")
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
    st.title("Settings")
    fresh = {}
    for rel in ["docs/EVIDENCE_LEDGER.md", "research/results/shadow_signals.csv",
                "logs/fills.csv", "state/macro_daily.csv"]:
        p = REPO / rel
        fresh[rel] = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M") \
            if p.exists() else "missing"
    st.write({"repository": str(REPO),
              "commit": sh_git("rev-parse", "--short", "HEAD"),
              "branch": sh_git("branch", "--show-current"),
              "last sync": sh_git("log", "-1", "--format=%ci %s"),
              "auto-refresh": "toggle in sidebar",
              "data freshness": fresh})
    st.caption("VPS status: run `python status.py` on the VPS (authoritative).")
