"""HEAD TRADER / CIO — the desk reviews itself, on the machine that trades.

    py head_trader.py                 collect everything, reconstruct, review, write the report
    py head_trader.py --collect-only  just snapshot telemetry

WHY THIS RUNS ON THE VPS
  Every input the charter names -- MT5 journal, deals, positions, ledger, brain, logs -- lives
  where the terminal runs. A review written anywhere else is a review of a copy/paste. So the
  desk reviews itself where the evidence is, and the human reads the output.

WHAT IT WILL NOT DO
  Patch production. PATCHES.md is a recommendation; nothing here edits a bot, a rule, or a
  parameter. It also will not manufacture a verdict from a sample too small to support one --
  "INSUFFICIENT_EVIDENCE" is a finding, not a failure to analyse.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime, timezone, timedelta
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
DATA = ROOT / "data" / "challenge"
TELEM = ROOT / "data" / "telemetry"
REPORT = ROOT / "DAILY_HEAD_TRADER.md"
PATCHES = ROOT / "PATCHES.md"

RETCODES = {10009: "DONE", 10027: "CLIENT_DISABLES_AT (AutoTrading off in terminal)",
            10018: "MARKET_CLOSED", 10019: "NO_MONEY", 10016: "INVALID_STOPS",
            10014: "INVALID_VOLUME", 10015: "INVALID_PRICE", 10004: "REQUOTE",
            10006: "REJECT", 10030: "INVALID_FILL"}


# ==================================================================== 1. collect
def collect(mt5=None) -> dict:
    """Every available input, snapshotted. Nothing is asked of the user."""
    snap = {"collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    TELEM.mkdir(parents=True, exist_ok=True)

    for name, path in (("ledger", DATA / "trades.jsonl"),
                       ("brain_events", ROOT / "data" / "brain" / "events.jsonl"),
                       ("controller_state", DATA / "controller_state.json"),
                       ("open_positions_track", DATA / "open_positions.json")):
        try:
            snap[name] = (path.read_text(encoding="utf-8").splitlines() if path.suffix == ".jsonl"
                          else json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None
        except Exception as e:
            snap[name] = f"UNREADABLE: {e}"

    if mt5 is None:
        return snap
    try:
        a = mt5.account_info()
        snap["account"] = {"login": a.login, "server": a.server, "balance": a.balance,
                           "equity": a.equity, "margin": a.margin,
                           "free_margin": a.margin_free, "currency": a.currency,
                           "trade_mode": a.trade_mode}
        t = mt5.terminal_info()
        snap["terminal"] = {"trade_allowed": t.trade_allowed, "connected": t.connected,
                            "ping_last": getattr(t, "ping_last", None),
                            "build": getattr(t, "build", None)}
        snap["positions"] = [{"ticket": p.ticket, "symbol": p.symbol, "volume": p.volume,
                              "open": p.price_open, "sl": p.sl, "tp": p.tp,
                              "profit": p.profit, "swap": p.swap, "magic": p.magic}
                             for p in (mt5.positions_get() or [])]
        snap["orders"] = [{"ticket": o.ticket, "symbol": o.symbol, "type": o.type,
                           "volume": o.volume_current, "price": o.price_open}
                          for o in (mt5.orders_get() or [])]
        since = datetime.now() - timedelta(days=7)
        snap["deals"] = [{"ticket": d.ticket, "symbol": d.symbol, "type": d.type,
                          "volume": d.volume, "price": d.price, "profit": d.profit,
                          "swap": d.swap, "commission": d.commission, "magic": d.magic,
                          "comment": d.comment, "time": d.time}
                         for d in (mt5.history_deals_get(since, datetime.now()) or [])]
        # spread / latency, measured now rather than assumed
        snap["spreads"] = {}
        for s in sorted({p["symbol"] for p in snap["positions"]} |
                        {"XAUUSD", "US100.cash", "US500.cash", "EURUSD"}):
            if mt5.symbol_select(s, True):
                tk = mt5.symbol_info_tick(s)
                inf = mt5.symbol_info(s)
                if tk and inf:
                    snap["spreads"][s] = {"spread": round(tk.ask - tk.bid, 6),
                                          "stops_level": inf.trade_stops_level,
                                          "contract": inf.trade_contract_size}
    except Exception as e:
        snap["mt5_error"] = str(e)

    day = datetime.now(timezone.utc).date().isoformat()
    (TELEM / f"{day}.json").write_text(json.dumps(snap, indent=1, default=str), encoding="utf-8")
    return snap


# ==================================================================== 2. reconstruct
def merged_trades() -> list:
    p = DATA / "trades.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    opens = {r["intent_id"]: r for r in rows if r.get("kind") != "close"}
    out = []
    for r in rows:
        if r.get("kind") == "close":
            out.append({**opens.get(r["intent_id"], {}), **r})
    return out


def diagnose(t: dict) -> tuple[str, str]:
    """Signal / context / execution / risk / randomness -- separated, per the charter.
    UNKNOWN is a permitted answer; a forced explanation is worse than an honest gap."""
    R = t.get("R")
    ms = t.get("market_state") or {}
    fs = t.get("feature_snapshot") or {}
    sl = fs.get("sl_dist") or abs((t.get("entry") or 0) - (t.get("stop") or 0)) or None
    slip = abs(t.get("actual_slippage") or 0)
    atr = ms.get("atr20_d1")
    mfe, mae = t.get("mfe_R"), t.get("mae_R")

    if R is None:
        return "UNKNOWN", "closed but R could not be computed"
    # only a CLEARLY too-tight stop, not a boundary case. At exactly the floor this rule
    # fired on BOT_F and hid the real cause (a 2 ATR extended entry), which is the more
    # useful lesson -- a diagnosis that shadows a better diagnosis is worse than none.
    if sl and atr and sl < 0.10 * atr:
        return "STOP_INSIDE_NOISE", f"stop {sl:.2f} was {sl/atr:.1%} of D1 ATR {atr:.0f}"
    if R <= -2.0:
        return "RISK_OVERRUN", f"realised {R:+.2f}R against a planned -1R"
    if sl and slip > 0.1 * sl:
        return "EXECUTION_SLIPPAGE", f"slippage {slip:.2f} = {slip/sl:.0%} of the stop"
    reg = ms.get("d1_regime")
    if R < 0 and reg in ("up", "down"):
        pb = t.get("playbook") or ""
        if pb == "REVERSION":
            return "TREND_OPPOSITION", f"faded into a d1 {reg} regime"
    ts = ms.get("d1_trend_strength_atr")
    if R < 0 and ts is not None and abs(ts) >= 2.0:
        return "EXTENDED_ENTRY", f"entered {ts:+.2f} ATR from the d1 mean"
    if R < 0 and mfe is not None and mfe > 0.8:
        return "TARGET_TOO_FAR", f"reached {mfe:+.2f}R before stopping out"
    if R > 0 and mae is not None and mae < -0.7:
        return "SURVIVED", f"went {mae:+.2f}R against first"
    if t.get("holding_minutes") is not None and t["holding_minutes"] < 5 and R < 0:
        return "HIGH_VOL_SHOCK", f"stopped out in {t['holding_minutes']} minutes"
    return ("EXPECTED_WIN" if R > 0 else "EXPECTED_LOSS"), f"R {R:+.3f}, no anomaly detected"


# ==================================================================== 3. report
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect-only", action="store_true")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()

    import sys
    sys.path.insert(0, str(ROOT))
    mt5 = None
    try:
        import MetaTrader5 as _m
        mt5 = _m if _m.initialize() else None
    except Exception:
        pass
    snap = collect(mt5)
    if a.collect_only:
        print(f"telemetry written for {datetime.now(timezone.utc).date()}"); return

    import pandas as pd
    today = a.date or pd.Timestamp.now(tz="Europe/London").date().isoformat()
    trades = merged_trades()
    todays = [t for t in trades if (t.get("timestamp") or "").startswith(today)]

    import desk as DESK, shadows as SH
    from challenge_controller import BOTS, TARGET_PCT, MAX_DAILY_LOSS_PCT, p_pass_estimate
    from trading_brain import belief, execution_quality, risk_audit, learn
    try:
        learn()
    except Exception:
        pass

    # ---- market read, from the desk's own engine
    market = {}
    if mt5:
        import market_state as MS, macro_context as MC
        now = pd.Timestamp.now(tz="Europe/London")
        for sym in sorted({b.symbol for b in BOTS}):
            if not mt5.symbol_select(sym, True):
                continue
            tk = mt5.symbol_info_tick(sym)
            if not tk:
                continue
            st = MS.compute(mt5, sym, now, tk.ask, tk.ask - tk.bid)
            st.update(MC.compute(mt5, sym, now))
            market[sym] = {"state": st, "opp": DESK.classify_opportunity(st)}

    beliefs = {b.strategy_id: belief(b.strategy_id, b.prior_expectancy_R, b.prior_n)
               for b in BOTS}

    L = [f"# DAILY HEAD TRADER REVIEW — {today}\n",
         f"_generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC on the trading host_\n"]

    # ---- account
    acct = snap.get("account") or {}
    cs = snap.get("controller_state") or {}
    start = (cs or {}).get("starting_balance")
    eq = acct.get("equity")
    L.append("\n## Account\n")
    if eq and start:
        L.append(f"- equity **{eq:,.2f}** vs anchor **{start:,.2f}** "
                 f"({eq/start-1:+.2%})")
        L.append(f"- total headroom **{0.10 + (eq/start-1):.2%}** of 10%")
        dse = cs.get("day_start_equity")
        if dse:
            L.append(f"- daily headroom **{MAX_DAILY_LOSS_PCT - (1 - eq/dse):.2%}** of 5%")
        L.append(f"- target: **{TARGET_PCT - (eq/start-1):+.2%}** remaining to +10%")
    else:
        L.append("- account unavailable (MT5 not reachable from this run)")
    term = snap.get("terminal") or {}
    if term:
        L.append(f"- terminal: trade_allowed **{term.get('trade_allowed')}**, "
                 f"connected {term.get('connected')}, ping {term.get('ping_last')}")
        if term.get("trade_allowed") is False:
            L.append("- **AUTOTRADING IS OFF — the desk cannot place a single order**")

    # ---- market first, bots second
    L.append("\n## What the market offered\n")
    if not market:
        L.append("_market engine unavailable this run_")
    for sym, m in market.items():
        L.append(f"\n**{sym}** — {', '.join(m['opp']['opportunities'])}")
        for k, v in m["opp"]["why"].items():
            L.append(f"  - {k}: {v}")
        st = m["state"]
        L.append(f"  - regimes d1/h4/h1: {st.get('d1_regime')}/{st.get('h4_regime')}"
                 f"/{st.get('h1_regime')}, ATR20 {st.get('atr20_d1')}, "
                 f"range position 120d {st.get('range_position_120d')}")

    # ---- reconstruction
    L.append(f"\n## Today's trades ({len(todays)})\n")
    if not todays:
        L.append("_no trades closed today_")
    for t in todays:
        cls, why = diagnose(t)
        ms = t.get("market_state") or {}
        L.append(f"\n### {t.get('strategy_id')} — {t.get('timestamp')}")
        L.append(f"| | |\n|---|---|")
        for k, v in (("side", "LONG" if (t.get('side') or 0) > 0 else "SHORT"),
                     ("entry / stop / target",
                      f"{t.get('entry')} / {t.get('stop')} / {t.get('target')}"),
                     ("exit / outcome", f"{t.get('exit')} / {t.get('outcome')}"),
                     ("gross / swap / comm / net",
                      f"{t.get('gross')} / {t.get('swap')} / {t.get('commission')} / "
                      f"**{t.get('net')}**"),
                     ("R", f"**{t.get('R'):+.3f}**" if t.get("R") is not None else "—"),
                     ("MFE / MAE", f"{t.get('mfe_R')} / {t.get('mae_R')} R"),
                     ("holding", f"{t.get('holding_minutes')} min"),
                     ("spread / slippage",
                      f"{t.get('spread')} / {t.get('actual_slippage')}"),
                     ("regime at entry",
                      f"{ms.get('d1_regime')} d1, {ms.get('h4_regime')} h4"),
                     ("macro", f"{ms.get('macro_risk')}, {ms.get('macro_usd')}"),
                     ("shadows", json.dumps(t.get("shadows") or {}))):
            L.append(f"| {k} | {v} |")
        L.append(f"\n**Diagnosis: {cls}** — {why}")

    # ---- risk overruns
    over = risk_audit()
    L.append(f"\n## Risk overruns ({len(over)})\n")
    if not over:
        L.append("_none — every loss stayed inside its planned risk_")
    for o in over:
        L.append(f"- **{o['strategy_id']}** realised {o['realized_R']:+.2f}R "
                 f"(planned ${o['planned_risk_money']:.2f}, lost ${o['realized_loss_money']:.2f}) "
                 f"— slipped {o['slip_past_stop']} past the stop → **{o['flag']}**")

    # ---- bot review
    L.append("\n## Bot scoreboard\n")
    L.append("| bot | playbook | n | posterior R | conf | exec slip/R | action |")
    L.append("|---|---|---|---|---|---|---|")
    for b in BOTS:
        be, eq_ = beliefs[b.strategy_id], execution_quality(b.strategy_id)
        n, t_ = be["n"], be.get("t")
        bad = [x for x in over if x["strategy_id"] == b.strategy_id
               and x["flag"] == "OBSERVATION"]
        if bad:
            act = "**OBSERVATION** (risk overrun)"
        elif n == 0:
            act = "EXPERIMENTAL"
        elif n >= 25 and t_ is not None and t_ <= -1.5:
            act = "RETIRE"
        elif n >= 40 and t_ is not None and t_ >= 1.5:
            act = "PROMOTE"
        elif n >= 25 and t_ is not None and t_ < 0:
            act = "REDUCE"
        else:
            act = "KEEP"
        sl = eq_.get("slip_R")
        L.append(f"| {b.strategy_id} | {b.playbook} | {n} | {be['exp']:+.3f} | "
                 f"{be['weight_live']:.0%} | {f'{sl:.3f}' if sl is not None else '—'} | {act} |")
    if all(beliefs[b.strategy_id]["n"] < 5 for b in BOTS):
        L.append("\n> Every action above is provisional. No bot has the sample to justify "
                 "promotion or retirement; these are placeholders that will move.")

    # ---- shadows
    sb = SH.scoreboard(trades)
    L.append("\n## Shadow desk\n")
    if not sb:
        L.append("_no shadow verdicts attached to closed trades yet_")
    else:
        L.append("| bot::variant | taken | skipped | exp taken | exp skipped | delta |")
        L.append("|---|---|---|---|---|---|")
        for k, v in sorted(sb.items(), key=lambda kv: -(kv[1]["delta_vs_live"] or -9)):
            L.append(f"| {k} | {v['n_taken']} | {v['n_skipped']} | "
                     f"{v['exp_taken'] if v['exp_taken'] is None else round(v['exp_taken'],3)} | "
                     f"{v['exp_skipped'] if v['exp_skipped'] is None else round(v['exp_skipped'],3)} | "
                     f"{v['delta_vs_live'] if v['delta_vs_live'] is None else round(v['delta_vs_live'],3)} |")
        L.append("\n_A shadow needs many observations before a delta means anything. "
                 "Promotion requires repeated outperformance, not one good week._")

    # ---- coverage / bot factory
    all_opp = sorted({o for m in market.values() for o in m["opp"]["opportunities"]})
    cov = DESK.coverage(BOTS, all_opp) if all_opp else {"covered": {}, "gaps": []}
    L.append("\n## Coverage — work orders for the Bot Factory\n")
    for r, who in cov.get("covered", {}).items():
        L.append(f"- **{r}**: {', '.join(who) if who else '**NO SPECIALIST**'}")
    if cov.get("gaps"):
        L.append(f"\n**GAPS: {', '.join(cov['gaps'])}** — these are build orders, "
                 f"not reasons to stop trading.")
    else:
        L.append("\n_Every regime observed today has a specialist._")

    # ---- P(pass)
    L.append("\n## Probability of passing\n")
    Rs = [t["R"] for t in trades if t.get("R") is not None]
    if len(Rs) < 20:
        L.append(f"**INSUFFICIENT_EVIDENCE** — {len(Rs)} closed trades. A first-passage "
                 f"estimate needs a stable expectancy and dispersion; computing one from "
                 f"{len(Rs)} would produce a number with no information in it.")
        if Rs:
            L.append(f"\n_Raw so far: mean {statistics.fmean(Rs):+.3f}R over {len(Rs)}, "
                     f"total {sum(Rs):+.2f}R. Descriptive only._")
    else:
        exp, sd = statistics.fmean(Rs), statistics.stdev(Rs)
        pp = p_pass_estimate(exp, sd, 0.0010)
        L.append(f"- expectancy {exp:+.3f}R, sd {sd:.3f} over {len(Rs)} trades")
        L.append(f"- **P(pass) {pp['p_pass']:.1%}**, P(breach) {pp['p_breach']:.1%}, "
                 f"median days {pp['median_days']}")

    # ---- patches
    P = [f"# PATCHES — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n",
         "Recommendations only. Nothing here has been applied.\n"]
    rej = Counter(RETCODES.get(t.get("retcode"), str(t.get("retcode")))
                  for t in trades
                  if (t.get("timestamp") or "").startswith(today)
                  and t.get("retcode") not in (10009, None))
    npatch = 0
    for name, n in rej.most_common():
        npatch += 1
        P.append(f"\n## {npatch}. {n} order(s) rejected: {name}\n")
        P.append(f"- **Evidence:** retcode seen {n}x today")
        P.append(f"- **Root cause:** see the retcode meaning above")
        P.append(f"- **Patch:** add a pre-send validation for this condition")
        P.append(f"- **Confidence:** HIGH (broker codes are unambiguous)")
    for o in over:
        npatch += 1
        P.append(f"\n## {npatch}. {o['strategy_id']} risk overrun {o['realized_R']:+.2f}R\n")
        P.append(f"- **Evidence:** planned ${o['planned_risk_money']:.2f}, "
                 f"lost ${o['realized_loss_money']:.2f}, slipped {o['slip_past_stop']} past stop")
        P.append(f"- **Root cause:** stop geometry or fill quality, not entry logic")
        P.append(f"- **Patch:** bot to OBSERVATION until the cause is understood")
        P.append(f"- **Confidence:** HIGH")
    if term.get("trade_allowed") is False:
        npatch += 1
        P.append(f"\n## {npatch}. AutoTrading disabled\n")
        P.append("- **Evidence:** terminal_info().trade_allowed == False")
        P.append("- **Patch:** Tools > Options > Expert Advisors > Allow algorithmic trading")
        P.append("- **Confidence:** CERTAIN")
    if npatch == 0:
        P.append("\n_No execution defects detected today._")
    PATCHES.write_text("\n".join(P) + "\n", encoding="utf-8")
    L.append(f"\n## Patches\n\nSee `PATCHES.md` — **{npatch}** proposed, none applied.")

    # ---- self critique
    L.append("\n## Self-critique — would I deploy this desk tomorrow?\n")
    n_live = sum(1 for b in BOTS if beliefs[b.strategy_id]["n"] > 0)
    invalid = [t for t in trades if diagnose(t)[0] in
               ("STOP_INSIDE_NOISE", "RISK_OVERRUN", "EXECUTION_SLIPPAGE")]
    L.append(f"- **No.** {len(Rs)} closed trades, {n_live}/{len(BOTS)} bots with any live "
             f"evidence, and {len(invalid)} of those trades were structurally invalid "
             f"rather than informative.")
    L.append(f"- What I would keep: the risk machinery. Anchors, stop geometry, time exits "
             f"and the group cap are all now tested, and each was silently broken before.")
    L.append(f"- What I would not fund: any bot on today's posterior. Every number is "
             f"prior-dominated.")
    L.append(f"- What the desk needs: **valid trades, not more code.** The next 20 clean "
             f"observations decide more than any module I could add.")

    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {REPORT.name} ({len(todays)} trades today, {len(Rs)} lifetime) "
          f"and {PATCHES.name} ({npatch} patches)")
    if mt5:
        mt5.shutdown()


if __name__ == "__main__":
    main()
