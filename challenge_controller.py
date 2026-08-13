"""FTMO CHALLENGE LEARNING CONTROLLER — demo only. Live trades are the evidence.

    py challenge_controller.py --status          state + bot table, no trading
    py challenge_controller.py --dry-run         full decision path, prints intents, sends nothing
    py challenge_controller.py --live-demo       arms execution on the DEMO account

WHAT THIS IS FOR
  Backtests initialise a PRIOR. Live demo fills update it. A bot is retired because live evidence
  turns poor, not because historical evidence was incomplete. The controller allocates risk under
  uncertainty rather than waiting for certainty that never arrives.

WHAT IT WILL NOT DO
  - trade a non-demo account (hard gate, checked every cycle)
  - trade the wrong account (identity bound to config/guardian.env)
  - let a bot send its own orders (bots return intents; only this file authorises)
  - increase risk after a loss, martingale, average down, or remove a stop
  - change a bot's parameters. Bots are FROZEN within an epoch. Learning is allocation-level.

THE ONE NUMBER THAT MATTERS
  P(reach +10% before -10% or a -5% day). Not Sharpe, not CAGR. Bots are ranked on first-passage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, asdict, field
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
DATA = ROOT / "data" / "challenge"
TRADES = DATA / "trades.jsonl"
STATE = DATA / "controller_state.json"

# ---- FTMO 2-step, current verified objectives
TARGET_PCT = 0.10
MAX_DAILY_LOSS_PCT = 0.05
MAX_TOTAL_LOSS_PCT = 0.10
MIN_TRADING_DAYS = 4

# ---- risk policy. Predeclared, never adaptive to the last trade's outcome.
RISK_EXPERIMENTAL = 0.0010      # 0.10% while a bot is gathering its first evidence
RISK_ESTABLISHED = 0.0025       # 0.25% ceiling on demo, only after DEMO_PROVEN
MAX_CONCURRENT_RISK = 0.0075    # total open risk across all bots
EPOCH_TRADES = 20               # review cadence. NEVER review after a single loss.
MAX_ORDER_ATTEMPTS_PER_DAY = 3  # a rejected order may be retried, but not indefinitely
MAX_NOTIONAL_MULT = 3.0         # position notional vs equity -- a tight stop must not
                                # turn a 0.05% risk into a 3x-leveraged position
MIN_STOP_SPREAD_MULT = 30.0     # stop must clear the spread by this much to be tradable.
                                # 8x allowed spread alone to be 12.5% of R. First-passage
                                # simulation of a ZERO-EDGE system at 1% risk, 40k paths:
                                #   cost  2%R -> P(pass) 31.6%
                                #   cost  5%R -> P(pass) 20.8%
                                #   cost 10%R -> P(pass)  9.2%
                                # 30x caps spread at ~3% of R. Cost control is worth more
                                # than any entry rule the desk owns, and it needs no edge to
                                # collect. The ATR floor usually binds first; this is the net
                                # for instruments where ATR is small relative to spread.
MIN_STOP_ATR_FRAC = 0.15        # ...AND clear this fraction of the D1 ATR20. Spread alone is
                                # not a volatility floor: BOT_D passed the spread gate with a
                                # 6.1pt gold stop and was gapped 31pt through it for -6.07R.

# Recurring high-impact release times, London clock. NOT a calendar -- a calendar feed needs
# purchase approval and the MT5 Python API exposes none. These are the fixed clock slots the
# major US releases land in (CPI/NFP/PPI/retail 13:30, ISM/UoM 15:00, FOMC 19:00). Static,
# free, and it blocks NEW ENTRIES ONLY -- open positions keep their stops and targets.
EVENT_BLACKOUT_LONDON = [(13, 30), (15, 0), (19, 0)]
BLACKOUT_BEFORE_MIN, BLACKOUT_AFTER_MIN = 10, 20

# ---- promotion ladder
STAGES = ("IDEA", "BACKTESTED", "VALIDATED", "DEMO_CANDIDATE", "DEMO_PROVEN",
          "CHALLENGE_CANDIDATE", "RETIRED")
DEMO_PROVEN_MIN_TRADES = 40


# ==================================================================== bot interface
from bot_base import Bot, Signal  # noqa: F401  (re-exported)


# ==================================================================== bayesian scoring
def posterior(bot_stats: dict, prior_exp: float, prior_n: int) -> dict:
    """Shrink live expectancy toward the backtest prior by evidence weight.

    5 live wins do not beat 100 mildly profitable trades. The shrinkage makes that explicit
    instead of leaving it to judgement.
    """
    n = bot_stats.get("n", 0)
    if n == 0:
        return {"exp": prior_exp, "se": float("nan"), "n": 0, "weight_live": 0.0}
    live_exp = bot_stats["mean_R"]
    live_var = max(bot_stats.get("var_R", 1.0), 1e-6)
    # prior treated as prior_n pseudo-observations with the same dispersion
    k = min(prior_n, 200)
    w = n / (n + k) if (n + k) > 0 else 1.0
    exp = w * live_exp + (1 - w) * prior_exp
    se = math.sqrt(live_var / max(n, 1))
    return {"exp": exp, "se": se, "n": n, "weight_live": w}


def p_pass_estimate(exp_R: float, sd_R: float, risk_frac: float, n_sims=4000,
                    max_days=365, trades_per_day=1.0, seed=3) -> dict:
    """First-passage: P(+10% before -10% or a -5% day). The only ranking that matters."""
    import numpy as np
    if not (sd_R > 0) or exp_R != exp_R:
        return {"p_pass": float("nan"), "p_breach": float("nan"), "median_days": None}
    rng = np.random.default_rng(seed)
    npass = nbreach = 0
    days = []
    for _ in range(n_sims):
        eq, day, day_start = 1.0, 0, 1.0
        while day < max_days:
            k = rng.poisson(trades_per_day)
            day_start = eq
            for _t in range(k):
                r = rng.normal(exp_R, sd_R) * risk_frac
                eq *= (1 + r)
            day += 1
            if eq / day_start - 1 <= -MAX_DAILY_LOSS_PCT:
                nbreach += 1; break
            if eq - 1 <= -MAX_TOTAL_LOSS_PCT:
                nbreach += 1; break
            if eq - 1 >= TARGET_PCT and day >= MIN_TRADING_DAYS:
                npass += 1; days.append(day); break
    import numpy as np
    return {"p_pass": npass / n_sims, "p_breach": nbreach / n_sims,
            "median_days": float(np.median(days)) if days else None}


# ==================================================================== challenge state
@dataclass
class ChallengeState:
    equity: float
    balance: float
    starting_balance: float
    day_start_equity: float
    trading_days: int
    open_risk_pct: float

    @property
    def profit_pct(self) -> float:
        return self.equity / self.starting_balance - 1

    @property
    def profit_remaining(self) -> float:
        return TARGET_PCT - self.profit_pct

    @property
    def daily_headroom(self) -> float:
        """Fraction of THIS DAY's starting equity still available before the 5% rule."""
        used = 1 - self.equity / self.day_start_equity
        return MAX_DAILY_LOSS_PCT - used

    @property
    def total_headroom(self) -> float:
        return MAX_TOTAL_LOSS_PCT + self.profit_pct

    def veto(self, risk_pct: float) -> str | None:
        """A valid signal can still be refused because of challenge state."""
        if self.daily_headroom <= risk_pct * 2:
            return f"daily headroom {self.daily_headroom:.2%} too thin for {risk_pct:.2%} risk"
        if self.total_headroom <= risk_pct * 3:
            return f"total headroom {self.total_headroom:.2%} too thin"
        if self.open_risk_pct + risk_pct > MAX_CONCURRENT_RISK:
            return f"open risk {self.open_risk_pct:.2%} + {risk_pct:.2%} > cap"
        if self.profit_remaining <= 0 and self.trading_days >= MIN_TRADING_DAYS:
            return "target already reached -- stop trading"
        return None


def stop_geometry(sig, state: dict, info, spread: float) -> dict:
    """Approve, widen, or reject a stop BEFORE sizing.

    Risk is expressed in dollars first: if the stop must widen, the VOLUME falls to keep the
    dollar risk identical. Widening without resizing would silently increase monetary risk,
    which is the opposite of what this gate is for.
    """
    dist = sig.risk_distance()
    atr = state.get("atr20_d1")
    exc = state.get("m1_excursion_p90_60")
    need = []
    if spread:
        need.append(("spread", MIN_STOP_SPREAD_MULT * spread))
    if atr:
        need.append(("D1 ATR", MIN_STOP_ATR_FRAC * atr))
    if exc:
        need.append(("recent M1 excursion", 2.0 * exc))
    if not need:
        return {"ok": True, "reason": "no volatility reference available", "checks": {}}

    label, floor = max(need, key=lambda x: x[1])
    checks = {k: round(v, 4) for k, v in need}
    if dist >= floor:
        return {"ok": True, "reason": f"stop {dist:.2f} clears {label} floor {floor:.2f}",
                "checks": checks}
    if floor > 3 * dist:
        return {"ok": False, "checks": checks,
                "reason": f"stop {dist:.2f} is under a third of the {label} floor "
                          f"{floor:.2f} -- the setup is inside the noise, not mis-sized"}
    return {"ok": True, "widened_to": floor, "checks": checks,
            "reason": f"stop {dist:.2f} below {label} floor {floor:.2f}"}


def in_event_blackout(now_london) -> str | None:
    """Refuse NEW entries around scheduled US releases. Never touches an open position:
    yanking a stop or closing early during a spike is how a bad trade becomes a disaster."""
    for h, m in EVENT_BLACKOUT_LONDON:
        slot = now_london.normalize() + __import__("pandas").Timedelta(hours=h, minutes=m)
        delta = (now_london - slot).total_seconds() / 60
        if -BLACKOUT_BEFORE_MIN <= delta <= BLACKOUT_AFTER_MIN:
            return (f"event blackout {h:02d}:{m:02d} London "
                    f"({delta:+.0f}m) -- scheduled release window")
    return None


def brain_multiplier(bot: Bot) -> tuple[float, str]:
    """Ask the Brain what experience says about this bot. Bounded [0.5, 1.5] so a memory
    bug can never size a trade dangerously. Brain unavailable -> 1.0, desk keeps trading."""
    try:
        from trading_brain import recall
        r = recall(bot.strategy_id, bot.prior_expectancy_R, bot.prior_n)
        return max(0.5, min(1.5, r["risk_multiplier"])), r["why"]
    except Exception as e:
        return 1.0, f"brain unavailable ({e})"


def risk_for(bot: Bot, st: ChallengeState) -> float:
    """LOSS_AWARE + TARGET_AWARE + EXPERIENCE_AWARE. Never increases after a loss:
    the Brain's multiplier is a function of the whole history, not the last outcome."""
    base = bot.risk_override or (
        RISK_ESTABLISHED if bot.stage in ("DEMO_PROVEN", "CHALLENGE_CANDIDATE")
        else RISK_EXPERIMENTAL)
    mult, why = brain_multiplier(bot)
    bot.brain_note = why
    base = min(base * mult, RISK_ESTABLISHED)      # experience may not exceed the hard cap
    # taper as either boundary approaches, and as the target comes into reach
    hd = max(st.daily_headroom / MAX_DAILY_LOSS_PCT, 0.0)
    ht = max(st.total_headroom / MAX_TOTAL_LOSS_PCT, 0.0)
    taper = min(1.0, hd, ht)
    if st.profit_remaining < 0.02:            # within 2% of target: protect the pass
        taper = min(taper, 0.5)
    return round(base * taper, 6)


def trend_context(mt5, symbol, price) -> dict:
    """Daily-timeframe context attached to EVERY signal.

    Recorded, not acted on. Filtering entries on trend before measuring whether trend
    predicts anything is how a backtest gets fitted -- the desk needs the labels on real
    trades first, then the Brain can measure whether aligned trades actually pay more.
    Until that measurement exists this changes no decision.
    """
    try:
        import numpy as np, pandas as pd
        r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 220)
        if r is None or len(r) < 60:
            return {"trend": "unknown", "bars": 0 if r is None else len(r)}
        d = pd.DataFrame(r)
        c = d["close"]
        sma20, sma50 = float(c.tail(20).mean()), float(c.tail(50).mean())
        sma200 = float(c.tail(200).mean()) if len(c) >= 200 else None
        tr = (d["high"] - d["low"]).tail(20).mean()
        prev_h, prev_l = float(d["high"].iloc[-2]), float(d["low"].iloc[-2])
        up = price > sma20 > sma50
        dn = price < sma20 < sma50
        return {"trend": "up" if up else "down" if dn else "mixed",
                "above_sma200": (price > sma200) if sma200 else None,
                "sma20": sma20, "sma50": sma50, "sma200": sma200,
                "atr20_d1": float(tr),
                "dist_sma20_atr": (price - sma20) / float(tr) if tr else None,
                "prev_day_range": prev_h - prev_l,
                "vs_prev_day": ("above" if price > prev_h else
                                "below" if price < prev_l else "inside")}
    except Exception as e:
        return {"trend": "unknown", "error": str(e)}


# ==================================================================== reconciliation
OPEN_STATE = DATA / "open_positions.json"


def reconcile(mt5, magic=990001) -> int:
    """Turn fills into evidence. Runs every cycle, before any new decision.

    Without this the ledger holds R=None forever and the Brain learns from nothing --
    the desk would trade for months and know exactly as much as on day one.

    Append-only: a close is a NEW record sharing the intent_id, never an edit of the
    pre-trade row. MFE/MAE are sampled each cycle while the position lives; they are
    running extremes, not evidence, so they live in a separate mutable file.
    """
    rows = load_trades()
    open_rows = {r["intent_id"]: r for r in rows
                 if r.get("ticket") and r.get("kind") != "close"}
    closed_ids = {r["intent_id"] for r in rows if r.get("kind") == "close"}
    pending = {k: v for k, v in open_rows.items() if k not in closed_ids}
    if not pending:
        return 0

    live = {p.ticket: p for p in (mt5.positions_get() or []) if p.magic == magic}
    track = json.loads(OPEN_STATE.read_text(encoding="utf-8")) if OPEN_STATE.exists() else {}
    n_closed = 0

    for iid, r in pending.items():
        tk = r["ticket"]
        st = track.setdefault(str(tk), {"mfe": 0.0, "mae": 0.0, "samples": 0})
        if tk in live:
            p = live[tk]
            excursion = (p.price_current - r["entry"]) * r["side"]
            st["mfe"] = max(st["mfe"], excursion)
            st["mae"] = min(st["mae"], excursion)
            st["samples"] += 1
            continue

        # gone from the book -> closed. Reconstruct from the broker's own deals.
        deals = mt5.history_deals_get(position=tk)
        if not deals:
            # not yet in history; try again next cycle rather than guessing
            continue
        d = sorted(deals, key=lambda x: x.time)
        net = sum(x.profit + x.swap + x.commission for x in d)
        exit_px = d[-1].price
        risk_money = r["risk_pct"] * r["account_equity"]
        R = net / risk_money if risk_money else None
        dist = abs(r["entry"] - r["stop"])
        if abs(exit_px - r["target"]) < abs(exit_px - r["stop"]):
            outcome = "target"
        elif abs(exit_px - r["stop"]) <= dist * 0.25:
            outcome = "stop"
        else:
            outcome = "time_or_manual"

        append_trade({
            "kind": "close", "intent_id": iid, "strategy_id": r["strategy_id"],
            "ticket": tk, "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "exit": exit_px, "gross": sum(x.profit for x in d),
            "swap": sum(x.swap for x in d), "commission": sum(x.commission for x in d),
            "net": net, "R": R, "outcome": outcome,
            "mfe": st["mfe"], "mae": st["mae"], "mfe_R": st["mfe"] / dist if dist else None,
            "mae_R": st["mae"] / dist if dist else None, "samples": st["samples"],
            "holding_minutes": int((d[-1].time - d[0].time) / 60),
        })
        track.pop(str(tk), None)
        n_closed += 1
        print(f"  CLOSED {r['strategy_id']} {outcome} R={R:+.3f} net={net:+.2f} "
              f"(swap {sum(x.swap for x in d):+.2f})  MFE {st['mfe']:+.2f} MAE {st['mae']:+.2f}")

    DATA.mkdir(parents=True, exist_ok=True)
    OPEN_STATE.write_text(json.dumps(track, indent=1), encoding="utf-8")
    return n_closed


def time_exits(mt5, acct, bots, dry_run=False, magic=990001) -> int:
    """Close positions whose session has ended. THE MISSING HALF OF EVERY STRATEGY.

    BOT_A held gold for 23 hours against a spec that says flat by 16:00 London. A broker
    stop/target is only two of the three exits every one of these bots was measured with;
    without the time exit the desk trades a strategy nobody backtested, and pays overnight
    financing that the whole intraday premise exists to avoid.

    PROOF BEFORE CLOSING -- required before any automatic close:
      account : the position's login must equal the connected demo account
      symbol  : must match the ledger row that opened it
      ticket  : must exist in the live book right now
      action  : the ledger row must name a bot whose session has demonstrably ended
    Anything unproven is skipped and reported, never closed on assumption.
    """
    import pandas as pd
    now = pd.Timestamp.now(tz="Europe/London")
    rows = {r["intent_id"]: r for r in load_trades() if r.get("kind") != "close"}
    by_ticket = {r["ticket"]: r for r in rows.values() if r.get("ticket")}
    by_id = {b.strategy_id: b for b in bots}
    n = 0

    for p in (mt5.positions_get() or []):
        if p.magic != magic:
            continue                                  # not ours -- never touch it
        row = by_ticket.get(p.ticket)
        if not row:
            print(f"  !! position {p.ticket} {p.symbol} has magic {magic} but NO ledger row "
                  f"-- NOT closing, manual review"); continue
        if row["symbol"] != p.symbol:
            print(f"  !! ticket {p.ticket} symbol {p.symbol} != ledger {row['symbol']} "
                  f"-- NOT closing"); continue
        bot = by_id.get(row["strategy_id"])
        if bot is None:
            print(f"  !! ticket {p.ticket} names unknown bot {row['strategy_id']} "
                  f"-- NOT closing"); continue
        eh, em = getattr(bot, "EXIT_H", None), getattr(bot, "EXIT_M", 0)
        if eh is None:
            continue                                  # bot declares no time exit
        opened = pd.Timestamp(row["timestamp"])
        cut = opened.normalize() + pd.Timedelta(hours=eh, minutes=em)
        if cut <= opened:
            cut += pd.Timedelta(days=1)
        if now < cut:
            continue

        held = int((now - opened).total_seconds() // 60)
        print(f"  TIME EXIT {row['strategy_id']} ticket {p.ticket} {p.symbol} "
              f"held {held}m, session ended {cut:%Y-%m-%d %H:%M} London")
        if dry_run:
            print("     DRY RUN -- not sent"); continue
        tick = mt5.symbol_info_tick(p.symbol)
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol,
               "volume": float(p.volume), "position": p.ticket,
               "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
               "price": tick.bid if p.type == 0 else tick.ask,
               "deviation": 20, "magic": magic, "comment": "time_exit",
               "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
        res = mt5.order_send(req)
        rc = getattr(res, "retcode", None)
        print(f"     close -> {rc} @ {getattr(res, 'price', None)}")
        if rc == mt5.TRADE_RETCODE_DONE:
            n += 1
        else:
            print(f"     !! TIME EXIT FAILED -- position still open, will retry next cycle")
    return n


# mandatory context. A trade whose state is missing cannot teach the desk anything, so it is
# not worth 0.05% -- and a NULL regime must never be silently read as "neutral".
MANDATORY_STATE = ("d1_regime", "h4_regime", "h1_regime", "atr20_d1", "ms_labels")


def preflight(mt5, acct, trades) -> list:
    """Instrumentation checks BEFORE any window opens. A failure here is a DESK FAULT, not a
    market veto: the desk is broken, so it must not trade and must say exactly why.

    Four separate faults have already reported healthy numbers while being wrong (inert
    headroom, missing time exits, a silent anchor fallback, a 3-hour clock). Every one was
    found by comparing output to ground truth. This does that comparison automatically.
    """
    import pandas as pd
    from datetime import datetime, timezone
    import market_state as MS
    fails = []

    def check(name, ok, detail=""):
        if not ok:
            fails.append(f"{name}: {detail}")

    check("account_identity", acct is not None and acct.login == 1514166963,
          f"login {getattr(acct, 'login', None)} != 1514166963")
    check("account_is_demo", acct is not None and acct.trade_mode == 0,
          f"trade_mode {getattr(acct, 'trade_mode', None)} is not demo")
    term = mt5.terminal_info()
    check("algotrading_enabled", term is not None and term.trade_allowed,
          "AlgoTrading is OFF in the terminal -- every order will retcode 10027")
    check("mt5_connected", term is not None and term.connected, "terminal not connected")

    off = MS.broker_utc_offset(mt5, "XAUUSD")
    check("broker_offset_sane", pd.Timedelta(hours=-14) <= off <= pd.Timedelta(hours=14),
          f"offset {off} is implausible")
    skew = MS.clock_skew(mt5, "XAUUSD")
    if abs(skew.total_seconds()) > 120 and False:
        # a WARNING, not a fault: the conversion is self-consistent either way, but a host
        # clock minutes off true time shifts every session window by that much.
        print(f"  ! CLOCK SKEW {skew.total_seconds():+.0f}s from a quarter-hour boundary "
              f"-- run 'w32tm /resync' on this host; session windows are shifted by this much")

    r = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M1, 0, 5)
    check("xauusd_available", r is not None and len(r) > 0, "no XAUUSD M1 data")
    if r is not None and len(r):
        bar = MS.to_london(pd.DataFrame(r)["time"], off).iloc[-1]
        bnow = MS.broker_now_london(mt5, "XAUUSD")
        age = abs((bnow - bar).total_seconds())
        # measured against the BROKER's own clock, so host drift cannot fail this
        check("fresh_m1_data", age < 900, f"newest M1 bar is {age/60:.0f} minutes old")
        host_gap = abs((pd.Timestamp.now(tz="Europe/London") - bnow).total_seconds())
        if host_gap > 120:
            print(f"  ! HOST CLOCK is {host_gap/60:.1f} min from the broker's. Session windows "
                  f"are UNAFFECTED (offset is hour-rounded), but fix it: the hypervisor time "
                  f"provider usually needs disabling before w32time will hold.")

    st = MS.compute(mt5, "XAUUSD", pd.Timestamp.now(tz="Europe/London"),
                    (mt5.symbol_info_tick("XAUUSD").ask if mt5.symbol_info_tick("XAUUSD")
                     else 0), 0.5)
    missing = [k for k in MANDATORY_STATE if st.get(k) in (None, "")]
    check("market_state_complete", not missing,
          f"DATA_INTEGRITY -- missing {', '.join(missing)} (d1_bars={st.get('d1_bars')})")

    stale = [p for p in (mt5.positions_get() or []) if p.magic == 990001]
    yday = (pd.Timestamp.now(tz="Europe/London") - pd.Timedelta(hours=24))
    old = [p for p in stale
           if pd.Timestamp(p.time, unit="s", tz="UTC") - off < yday]
    check("no_stale_position", not old,
          f"{len(old)} position(s) older than 24h still open: "
          f"{[p.ticket for p in old]}")

    try:
        anchors = challenge_anchors(acct, trades)
        cs = ChallengeState(**anchors)
        check("headroom_sane", -0.11 < cs.profit_pct < 0.20 and cs.total_headroom > 0,
              f"profit {cs.profit_pct:.2%}, total headroom {cs.total_headroom:.2%}")
        check("anchor_present", anchors["starting_balance"] > 0, "no starting balance anchor")
    except Exception as e:
        check("challenge_state", False, f"unreadable: {e}")

    for name, path in (("trade_ledger_writable", TRADES),
                       ("brain_ledger_writable", ROOT / "data" / "brain" / "events.jsonl")):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8"):
                pass
            check(name, True)
        except Exception as e:
            check(name, False, str(e))
    return fails


def challenge_anchors(acct, trades) -> dict:
    """The two numbers FTMO actually measures against, PERSISTED.

    They were being re-read from the live account every cycle, which set
    starting_balance = current balance and day_start_equity = current equity. Both headrooms
    therefore computed as full, always: the desk reported 5.00%/10.00% while $520 down, and
    would have reported the same at -9%. Every drawdown veto was dead code.

    An anchor is written ONCE and never recomputed from a number it is supposed to bound.
    """
    import pandas as pd
    STATE.parent.mkdir(parents=True, exist_ok=True)
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    today = pd.Timestamp.now(tz="Europe/London").date().isoformat()

    if not st.get("starting_balance"):
        # FTMO measures drawdown against the INITIAL DEPOSIT, not against whatever the
        # balance happened to be when this desk started. Read the balance deal from broker
        # history; only fall back to reconstruction if the broker cannot tell us.
        st["starting_balance"] = st["source"] = None
        try:
            import MetaTrader5 as _m
            # MT5 wants NAIVE datetimes. Passing a tz-aware one makes history_deals_get
            # fail, which the fallback then hid -- a silent fallback on the number every
            # drawdown limit is measured against is not an acceptable failure mode.
            deals = _m.history_deals_get(datetime(2000, 1, 1), datetime.now())
            if deals is None:
                print(f"  anchor: history_deals_get returned None {_m.last_error()}")
            bal = [d for d in (deals or []) if d.type == _m.DEAL_TYPE_BALANCE and d.profit > 0]
            if bal:
                st["starting_balance"] = float(min(bal, key=lambda d: d.time).profit)
                st["source"] = "broker initial deposit"
            else:
                print(f"  anchor: no positive balance deal in {len(deals or [])} deals")
        except Exception as e:
            print(f"  anchor: broker deposit unreadable ({e})")
        if not st["starting_balance"]:
            realised = sum(t.get("net") or 0 for t in trades if t.get("kind") == "close")
            st["starting_balance"] = float(acct.balance) - realised
            st["source"] = "RECONSTRUCTED from ledger -- deposit unreadable, see above"
            print(f"  !! ANCHOR FALLBACK: drawdown will be measured against "
                  f"{st['starting_balance']:.2f}, not the deposit")
        st["anchored_on"] = today
        print(f"  ANCHOR SET: starting balance {st['starting_balance']:.2f} "
              f"({st['source']})")

    if st.get("day") != today:
        st["day"] = today
        st["day_start_equity"] = float(acct.equity)
        print(f"  NEW TRADING DAY {today}: day-start equity {acct.equity:.2f}")

    STATE.write_text(json.dumps(st, indent=1), encoding="utf-8")

    open_risk = 0.0
    by_ticket = {t["ticket"]: t for t in trades if t.get("ticket") and t.get("kind") != "close"}
    closed = {t["intent_id"] for t in trades if t.get("kind") == "close"}
    for t in by_ticket.values():
        if t["intent_id"] not in closed:
            open_risk += t.get("risk_pct") or 0.0

    return {"equity": float(acct.equity), "balance": float(acct.balance),
            "starting_balance": float(st["starting_balance"]),
            "day_start_equity": float(st["day_start_equity"]),
            "trading_days": len({t.get("timestamp", "")[:10] for t in trades
                                 if t.get("kind") != "close"}),
            "open_risk_pct": open_risk}


# ==================================================================== ledger
def append_trade(rec: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    with TRADES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def load_trades() -> list:
    if not TRADES.exists():
        return []
    return [json.loads(l) for l in TRADES.read_text(encoding="utf-8").splitlines() if l.strip()]


def bot_stats(sid: str) -> dict:
    ts = [t for t in load_trades() if t.get("strategy_id") == sid and t.get("R") is not None]
    if not ts:
        return {"n": 0}
    import numpy as np
    R = np.array([t["R"] for t in ts], float)
    gp, gl = R[R > 0].sum(), -R[R < 0].sum()
    eq = (1 + R * 0.0025).cumprod()
    return {"n": len(R), "mean_R": float(R.mean()), "var_R": float(R.var(ddof=1)) if len(R) > 1 else 1.0,
            "sd_R": float(R.std(ddof=1)) if len(R) > 1 else float("nan"),
            "wins": int((R > 0).sum()), "losses": int((R <= 0).sum()),
            "pf": float(gp / gl) if gl > 0 else float("inf"),
            "max_dd": float((eq / np.maximum.accumulate(eq) - 1).min()),
            "avg_slippage": float(np.mean([t.get("actual_slippage", 0) or 0 for t in ts])),
            "avg_spread": float(np.mean([t.get("spread", 0) or 0 for t in ts]))}


def diagnose(trade: dict, stats: dict) -> str:
    """One label per closed trade. Never triggers a parameter change."""
    if stats.get("n", 0) < 10:
        return "INSUFFICIENT_DATA"
    slip = abs(trade.get("actual_slippage", 0) or 0)
    if slip > 3 * max(stats.get("avg_slippage", 0.01), 0.01):
        return "EXECUTION_PROBLEM"
    R = trade.get("R", 0)
    sd = stats.get("sd_R", 1.0)
    if R < stats["mean_R"] - 3 * sd:
        return "REGIME_MISMATCH"
    if stats["n"] >= 30 and stats["mean_R"] < -0.5 * abs(sd) / math.sqrt(stats["n"]) * 2:
        return "MODEL_DRIFT"
    return "EXPECTED_WIN" if R > 0 else "EXPECTED_LOSS"


# ==================================================================== breakout family
class SessionRangeBreakout(Bot):
    """Shared mechanic: break of the pre-session range, flat before rollover.

    ONE implementation, configured per bot. A copy-pasted second version is how the ablation
    module went stale silently -- if this logic is wrong it must be wrong for every bot at once,
    so live evidence compares like with like.

    Stops are either fixed (SL/TP in price units) or a multiple of the pre-range (SL_MULT/
    TP_MULT). The multiple form is what makes the mechanic portable across instruments: a $30
    stop is a sane gold stop and a nonsense index stop.
    """
    PRE_MIN = 90
    ENTRY_H = ENTRY_M = 0
    EXIT_H, EXIT_M = 16, 0
    SL = TP = None                    # fixed distance, price units
    SL_MULT = TP_MULT = None          # or: fraction of the pre-session range
    MIN_RANGE = 0.0                   # refuse a range too tight to survive the spread

    def generate_signal(self, ctx) -> Signal | None:
        import pandas as pd
        now = ctx["now_london"]
        bars = ctx["m1"]                       # DataFrame indexed in Europe/London
        if bars is None or len(bars) < self.PRE_MIN + 5:
            return self._no(f"only {0 if bars is None else len(bars)} M1 bars, "
                            f"need {self.PRE_MIN + 5}")
        day = now.normalize()
        t0 = day + pd.Timedelta(hours=self.ENTRY_H, minutes=self.ENTRY_M)
        cut = day + pd.Timedelta(hours=self.EXIT_H, minutes=self.EXIT_M)
        if not (t0 <= now < cut):
            return self._no(f"outside window: {now:%H:%M} London, opens "
                            f"{self.ENTRY_H:02d}:{self.ENTRY_M:02d} closes "
                            f"{self.EXIT_H:02d}:{self.EXIT_M:02d}")
        if ctx.get("traded_today", {}).get(self.strategy_id):
            return self._no("already traded today (one trade per session)")
        pre = bars[(bars.index >= t0 - pd.Timedelta(minutes=self.PRE_MIN)) & (bars.index < t0)]
        if len(pre) < 30:
            return self._no(f"pre-session range has {len(pre)} bars, need 30 "
                            f"(market closed or data gap)")
        hi, lo = float(pre["high"].max()), float(pre["low"].min())
        rng = hi - lo
        bid, ask = ctx["bid"], ctx["ask"]
        spread = ask - bid
        if rng < max(self.MIN_RANGE, 4 * spread):
            return self._no(f"pre-range {rng:.2f} inside the noise "
                            f"(spread {spread:.2f}, need > {max(self.MIN_RANGE, 4*spread):.2f})")
        if ask >= hi:
            side, lvl = 1, hi
        elif bid <= lo:
            side, lvl = -1, lo
        else:
            return self._no(f"no break: bid/ask {bid:.2f}/{ask:.2f} inside "
                            f"[{lo:.2f}, {hi:.2f}], needs {hi-ask:+.2f} up or {lo-bid:+.2f} down")

        # FIRST break only. The frozen backtest takes the first crossing and stops looking;
        # a bot that re-fires on the third poke at the level hours later is trading a
        # DIFFERENT strategy than the one that produced the prior, and its live record would
        # not be evidence about that strategy at all.
        session = bars[(bars.index >= t0) & (bars.index < now)]
        if len(session):
            broke = (session["high"].max() >= hi) if side > 0 else (session["low"].min() <= lo)
            if broke:
                first = (session[session["high"] >= hi] if side > 0
                         else session[session["low"] <= lo]).index[0]
                return self._no(f"first break already happened at {first:%H:%M} "
                                f"({int((now-first).total_seconds()//60)}m ago) -- "
                                f"not chasing a re-test")
        sl = self.SL if self.SL is not None else rng * self.SL_MULT
        tp = self.TP if self.TP is not None else rng * self.TP_MULT
        if sl < MIN_STOP_SPREAD_MULT * spread:
            return self._no(f"stop {sl:.2f} too tight vs spread {spread:.2f} "
                            f"(need {MIN_STOP_SPREAD_MULT}x) -- costs would dominate")
        entry = ask if side > 0 else bid
        return Signal(self.strategy_id, self.strategy_version, now.isoformat(), self.symbol,
                      side, "market", entry, entry - side * sl, entry + side * tp,
                      int((cut - now).total_seconds() // 60),
                      ["pre_range_break", f"level={lvl:.2f}"],
                      {"pre_high": hi, "pre_low": lo, "pre_range": rng, "sl_dist": sl,
                       "tp_dist": tp, "spread": spread,
                       "minutes_since_entry": int((now - t0).total_seconds() // 60)})


# ==================================================================== BOT_A
class GoldBreakout0630(SessionRangeBreakout):
    """BOT_A. Frozen spec: intraday-lab/gold0630/GOLD_BREAKOUT_FROZEN.md

    Breakout of the 90-minute pre-06:30-London range. TP $60 / SL $30. Flat by 16:00 London,
    so it pays ZERO overnight financing -- which is what killed the frozen portfolio.

    PRIOR from backtest: +0.39R over 60 days, t=+2.42, BUT chosen as best of 14 configurations,
    so the honest prior shrinks it. prior_n is deliberately small: this prior is weak and live
    evidence should dominate quickly.
    """
    playbook = "BREAKOUT"
    primary = {"EXPANSION", "WEAK_TREND"}
    secondary = {"STRONG_TREND"}
    avoids = {"COMPRESSION", "EXTENDED"}
    strategy_id = "BOT_A_gold_0630_breakout"
    strategy_version = "1.2.0"       # shared base; parameters unchanged
    symbol = "XAUUSD"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R = 0.15        # shrunk from +0.39 for best-of-14 selection
    prior_n = 30

    TP, SL, PRE_MIN = 60.0, 30.0, 90
    ENTRY_H, ENTRY_M, EXIT_H, EXIT_M = 6, 30, 16, 0


# ==================================================================== BOT_B
class IndexBreakoutUSOpen(SessionRangeBreakout):
    """BOT_B. US cash open, NAS100.

    WHY THIS ONE, and not a fourteenth gold variant: the hourly control measured 50-60% larger
    excursions in the 12:30-14:30 London window than at 06:30. Entry is the 14:30 US cash open,
    breaking the 13:00-14:30 pre-open range. Flat by 20:00 London -- no financing, same as A.

    Different symbol, different session, different driver (US equity open vs London gold fix),
    so its trades are close to independent of BOT_A's. Two correlated bots would double the risk
    while adding almost no evidence.

    PRIOR = 0.00R, prior_n = 10. This bot has NO backtest and is not waiting for one. The prior
    is deliberately empty and light so live trades dominate the posterior after ~10 of them.
    It ships at 0.10% experimental risk; the desk finds out by trading, not by fitting.

    Stops are 0.5x / 1.0x the pre-open range rather than fixed points -- an index needs
    volatility-scaled distances, and a fixed gold-sized stop would be meaningless here.
    """
    playbook = "BREAKOUT"
    primary = {"EXPANSION", "WEAK_TREND"}
    secondary = {"STRONG_TREND"}
    avoids = {"COMPRESSION", "EXTENDED", "TRANSITION"}
    strategy_id = "BOT_B_nas100_usopen_breakout"
    strategy_version = "1.0.0"
    symbol = "US100.cash"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R = 0.00        # no backtest. none claimed.
    prior_n = 10                     # so ~10 live trades outweigh the prior

    SL_MULT, TP_MULT, PRE_MIN = 0.5, 1.0, 90
    ENTRY_H, ENTRY_M, EXIT_H, EXIT_M = 14, 30, 20, 0


# ==================================================================== BOT_C
class SP500LondonBreakout(SessionRangeBreakout):
    """BOT_C. US500 on the LONDON session, not the US open.

    Deliberately NOT the US open: SP500 and NAS100 run ~0.9 correlated in the first US hour,
    so a US-open S&P bot would mostly re-observe BOT_B at double the risk. On the London
    session the driver is European flow, which BOT_B never sees.
    """
    playbook = "BREAKOUT"
    primary = {"EXPANSION", "WEAK_TREND"}
    secondary = {"STRONG_TREND"}
    avoids = {"COMPRESSION", "EXTENDED"}
    strategy_id = "BOT_C_sp500_london_breakout"
    strategy_version = "1.0.0"
    symbol = "US500.cash"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R, prior_n = 0.00, 10
    risk_override = 0.0005
    SL_MULT, TP_MULT, PRE_MIN = 0.5, 1.0, 90
    ENTRY_H, ENTRY_M, EXIT_H, EXIT_M = 8, 0, 16, 30


# ==================================================================== BOT_D
class GoldNYBreakout(SessionRangeBreakout):
    """BOT_D. Gold at the NY open -- same instrument as BOT_A, different session.

    A and D share an asset, so their trades are NOT independent; the Brain will see that as
    correlated evidence and it is worth having anyway, because it directly answers a question
    the desk cannot otherwise settle: is BOT_A's edge about GOLD, or about 06:30?
    """
    playbook = "BREAKOUT"
    primary = {"EXPANSION", "WEAK_TREND"}
    secondary = {"STRONG_TREND"}
    avoids = {"COMPRESSION", "EXTENDED"}
    strategy_id = "BOT_D_gold_ny_breakout"
    strategy_version = "1.0.0"
    symbol = "XAUUSD"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R, prior_n = 0.00, 10
    risk_override = 0.0005
    SL_MULT, TP_MULT, PRE_MIN = 0.5, 1.0, 90
    ENTRY_H, ENTRY_M, EXIT_H, EXIT_M = 14, 30, 20, 0


# ==================================================================== BOT_E
class EURUSDLondonBreakout(SessionRangeBreakout):
    """BOT_E. EURUSD London open. FX, not an index or a metal.

    NOT the news bot you asked for. A news bot needs a scheduled-event calendar with
    embargo timestamps; this desk has no such feed and buying one needs your approval, so
    inventing an event list would be fabricating data. FX at the London open is the nearest
    honest thing already available: different market structure, different participants,
    different liquidity cycle. Say the word and I will spec the calendar acquisition.
    """
    playbook = "BREAKOUT"
    primary = {"EXPANSION", "WEAK_TREND"}
    secondary = {"STRONG_TREND"}
    avoids = {"COMPRESSION", "EXTENDED"}
    strategy_id = "BOT_E_eurusd_london_breakout"
    strategy_version = "1.0.0"
    symbol = "EURUSD"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R, prior_n = 0.00, 10
    risk_override = 0.0005
    SL_MULT, TP_MULT, PRE_MIN = 0.5, 1.0, 90
    ENTRY_H, ENTRY_M, EXIT_H, EXIT_M = 8, 0, 17, 0


# ==================================================================== BOT_F
class VWAPReversion(Bot):
    """BOT_F. The only bot on the desk that is not a breakout.

    Every other bot profits when a move continues. This one profits when a move exhausts, so
    its returns should be NEGATIVELY correlated with the rest -- which is worth more to a
    challenge than a sixth trend bot would be. It fades BOT_B's instrument on purpose: when
    breakouts fail, this is what the desk earns instead.

    Entry: price >= K sigma from the session VWAP, fade toward VWAP. Stop beyond the extreme.
    No averaging down, one entry, hard stop -- a mean-reversion bot without a stop is how
    accounts die, and this one is stopped like every other bot here.
    """
    playbook = "REVERSION"
    primary = {"RANGE"}
    secondary = {"COMPRESSION"}
    # THE FIX FOR 2026-08-13: this bot shorted 2.02 ATR above its mean in a TRANSITION.
    # Declared, not filtered -- a fade has no meaning without a mean that holds.
    avoids = {"STRONG_TREND", "WEAK_TREND", "TRANSITION", "EXPANSION", "EXTENDED"}
    strategy_id = "BOT_F_nas100_vwap_reversion"
    strategy_version = "1.1.0"
    symbol = "US100.cash"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R, prior_n = 0.00, 10
    risk_override = 0.0005

    SESSION_H, SESSION_M = 14, 30        # VWAP anchored to the US cash open
    ENTRY_FROM_H, EXIT_H, EXIT_M = 15, 20, 0
    K_SIGMA = 2.0
    STOP_MULT, TARGET_FRAC = 1.0, 0.6    # stop 1 sigma beyond; take 60% of the way back

    def generate_signal(self, ctx) -> Signal | None:
        import numpy as np, pandas as pd
        now, bars = ctx["now_london"], ctx["m1"]
        if bars is None or len(bars) < 60:
            return self._no(f"only {0 if bars is None else len(bars)} M1 bars, need 60")
        day = now.normalize()
        t0 = day + pd.Timedelta(hours=self.SESSION_H, minutes=self.SESSION_M)
        start = day + pd.Timedelta(hours=self.ENTRY_FROM_H)
        cut = day + pd.Timedelta(hours=self.EXIT_H, minutes=self.EXIT_M)
        if not (start <= now < cut):
            return self._no(f"outside window: {now:%H:%M} London, opens "
                            f"{self.ENTRY_FROM_H:02d}:00 closes {self.EXIT_H:02d}:00")
        if ctx.get("traded_today", {}).get(self.strategy_id):
            return self._no("already traded today")
        s = bars[bars.index >= t0]
        if len(s) < 30:
            return self._no(f"session has {len(s)} bars since {t0:%H:%M}, need 30")
        tp_ = (s["high"] + s["low"] + s["close"]) / 3
        vol = s["tick_volume"].replace(0, 1)
        vwap = float((tp_ * vol).cumsum().iloc[-1] / vol.cumsum().iloc[-1])
        sigma = float((s["close"] - vwap).std())
        if not (sigma > 0):
            return self._no("session sigma is zero -- no dispersion yet")
        bid, ask = ctx["bid"], ctx["ask"]
        mid = (bid + ask) / 2
        dev = (mid - vwap) / sigma
        if abs(dev) < self.K_SIGMA:
            return self._no(f"{dev:+.2f} sigma from VWAP {vwap:.2f}, "
                            f"need +-{self.K_SIGMA}")
        side = -1 if dev > 0 else 1               # fade the extension
        entry = ask if side > 0 else bid
        stop = entry - side * self.STOP_MULT * sigma
        target = entry + side * abs(mid - vwap) * self.TARGET_FRAC
        if abs(entry - stop) < MIN_STOP_SPREAD_MULT * (ask - bid):
            return self._no(f"stop {abs(entry-stop):.2f} too tight vs spread {ask-bid:.2f}")
        return Signal(self.strategy_id, self.strategy_version, now.isoformat(), self.symbol,
                      side, "market", entry, stop, target,
                      int((cut - now).total_seconds() // 60),
                      ["vwap_reversion", f"dev={dev:+.2f}sig"],
                      {"vwap": vwap, "sigma": sigma, "dev_sigma": dev,
                       "sl_dist": abs(entry - stop), "pre_range": sigma * 2,
                       "spread": ask - bid,
                       "minutes_since_entry": int((now - start).total_seconds() // 60)})


# ==================================================================== BOT_G
class H4PullbackContinuation(Bot):
    """BOT_G. The desk's first CONTINUATION specialist -- it fills a measured coverage gap.

    Every other bot needs a level to break or a mean that holds. In a confirmed trend the
    desk owned NOTHING: on 2026-08-13 h4_regime was 'up' and every specialist either avoided
    the state or had no signal. An opportunity class with no specialist is a gap you can see
    on day one without any evidence at all -- it is an inventory fact, not a forecast.

    Buys a pullback toward the H4 mean while H4 trend is confirmed, stopping beyond the
    swing that would end the trend. Deliberately NOT a breakout: it wants the move to
    already exist, which is the exposure the desk lacks.
    """
    playbook = "CONTINUATION"
    primary = {"STRONG_TREND"}
    secondary = {"WEAK_TREND", "EXPANSION"}
    avoids = {"RANGE", "COMPRESSION", "TRANSITION"}
    strategy_id = "BOT_G_nas100_h4_pullback"
    strategy_version = "1.0.0"
    symbol = "US100.cash"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R, prior_n = 0.00, 10
    risk_override = 0.0005

    ENTRY_H, EXIT_H, EXIT_M = 8, 20, 0
    PULLBACK_ATR = 0.5               # how close to the H4 mean counts as a pullback
    STOP_ATR, TARGET_ATR = 1.0, 2.0  # of H4 ATR

    def generate_signal(self, ctx) -> Signal | None:
        import pandas as pd
        now, st = ctx["now_london"], ctx.get("state") or {}
        day = now.normalize()
        if not (day + pd.Timedelta(hours=self.ENTRY_H) <= now
                < day + pd.Timedelta(hours=self.EXIT_H, minutes=self.EXIT_M)):
            return self._no(f"outside window: {now:%H:%M} London")
        if ctx.get("traded_today", {}).get(self.strategy_id):
            return self._no("already traded today")
        reg, atr = st.get("h4_regime"), st.get("h4_atr20")
        if reg not in ("up", "down"):
            return self._no(f"h4 regime is {reg}, needs a confirmed trend")
        if not atr:
            return self._no("no h4 ATR available")
        dev = st.get("h4_price_vs_sma20")
        if dev is None:
            return self._no("no h4 mean available")
        bid, ask = ctx["bid"], ctx["ask"]
        price = (bid + ask) / 2
        sma = price / (1 + dev) if dev != -1 else None
        if not sma:
            return self._no("h4 mean unresolvable")
        dist_atr = (price - sma) / atr
        side = 1 if reg == "up" else -1
        # a pullback: price has come BACK toward the mean, not extended away from it
        if side > 0 and not (0 <= dist_atr <= self.PULLBACK_ATR):
            return self._no(f"not a pullback: {dist_atr:+.2f} ATR from h4 mean, "
                            f"need 0..{self.PULLBACK_ATR}")
        if side < 0 and not (-self.PULLBACK_ATR <= dist_atr <= 0):
            return self._no(f"not a pullback: {dist_atr:+.2f} ATR from h4 mean")
        entry = ask if side > 0 else bid
        stop = entry - side * self.STOP_ATR * atr
        target = entry + side * self.TARGET_ATR * atr
        return Signal(self.strategy_id, self.strategy_version, now.isoformat(), self.symbol,
                      side, "market", entry, stop, target,
                      int((day + pd.Timedelta(hours=self.EXIT_H) - now).total_seconds() // 60),
                      ["h4_pullback_continuation", f"h4_{reg}", f"dist={dist_atr:+.2f}atr"],
                      {"h4_regime": reg, "h4_atr": atr, "dist_atr": dist_atr,
                       "sl_dist": abs(entry - stop), "pre_range": atr,
                       "spread": ask - bid, "minutes_since_entry": 0})


# ==================================================================== BOT_H
class LiquiditySweepReclaim(Bot):
    """BOT_H. The desk's TRANSITION specialist -- built to a measured coverage gap.

    On 2026-08-13 gold and US100 were both TRANSITION + EXTENDED + AT_HTF_LEVEL and the desk
    owned nothing that could act. Every existing specialist needs a level to BREAK (breakout),
    a mean that HOLDS (reversion), or a trend already CONFIRMED (continuation). None of those
    describe an unconfirmed market pushing through a reference and getting rejected.

    Mechanism: price trades beyond a higher-timeframe level, then closes back inside within
    RECLAIM_BARS. Fade in the reclaim direction, stop beyond the sweep extreme, target the
    session mean. The only bot here that requires a level to FAIL.

    Uses the shared market_state levels -- no new level logic, so a fix to those levels fixes
    this bot too.
    """
    playbook = "SWEEP"
    primary = {"TRANSITION", "AT_HTF_LEVEL"}
    secondary = {"RANGE", "EXTENDED"}
    avoids = {"STRONG_TREND"}
    strategy_id = "BOT_H_gold_sweep_reclaim"
    strategy_version = "1.0.0"
    symbol = "XAUUSD"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R, prior_n = 0.00, 10
    risk_override = 0.0005

    ENTRY_H, EXIT_H, EXIT_M = 7, 20, 0
    RECLAIM_BARS = 15            # a sweep must be rejected promptly to count as a sweep
    MIN_PIERCE_ATR = 0.05        # it must actually pierce, not just touch
    STOP_BUFFER_ATR, TARGET_ATR = 0.15, 1.0
    LEVELS = ("lvl_prev_day_high", "lvl_prev_day_low", "lvl_asia_high", "lvl_asia_low",
              "lvl_high_20d", "lvl_low_20d", "lvl_weekly_open")

    def generate_signal(self, ctx) -> Signal | None:
        import pandas as pd
        now, st, bars = ctx["now_london"], ctx.get("state") or {}, ctx["m1"]
        day = now.normalize()
        if not (day + pd.Timedelta(hours=self.ENTRY_H) <= now
                < day + pd.Timedelta(hours=self.EXIT_H, minutes=self.EXIT_M)):
            return self._no(f"outside window: {now:%H:%M} London")
        if ctx.get("traded_today", {}).get(self.strategy_id):
            return self._no("already traded today")
        atr = st.get("atr20_d1")
        if not atr:
            return self._no("no D1 ATR -- cannot size a pierce")
        if bars is None or len(bars) < self.RECLAIM_BARS + 5:
            return self._no("insufficient M1 history")
        w = bars[bars.index < now].tail(self.RECLAIM_BARS)
        if len(w) < self.RECLAIM_BARS:
            return self._no("insufficient closed bars in the reclaim window")

        bid, ask = ctx["bid"], ctx["ask"]
        first, close = float(w["close"].iloc[0]), float(w["close"].iloc[-1])
        hi, lo = float(w["high"].max()), float(w["low"].min())
        best = None
        for key in self.LEVELS:
            lvl = st.get(key)
            if not lvl:
                continue
            # A SWEEP IS A ROUND TRIP: price starts one side of the level, pierces through,
            # and comes back. Without the "started on this side" condition, price simply
            # closing above a level counts as a sweep of every level beneath it -- which is
            # a breakout, the exact opposite trade.
            if first < lvl and close < lvl and (hi - lvl) / atr >= self.MIN_PIERCE_ATR:
                cand = (-1, lvl, hi, (hi - lvl) / atr, key)
            elif first > lvl and close > lvl and (lvl - lo) / atr >= self.MIN_PIERCE_ATR:
                cand = (1, lvl, lo, (lvl - lo) / atr, key)
            else:
                continue
            if best is None or cand[3] > best[3]:
                best = cand
        if best is None:
            return self._no("no level swept and reclaimed in the last "
                            f"{self.RECLAIM_BARS} minutes")

        side, lvl, extreme, pierce, key = best
        entry = ask if side > 0 else bid
        stop = extreme - side * self.STOP_BUFFER_ATR * atr
        target = entry + side * self.TARGET_ATR * atr
        if abs(entry - stop) < 1e-9:
            return self._no("degenerate stop")
        return Signal(self.strategy_id, self.strategy_version, now.isoformat(), self.symbol,
                      side, "market", entry, stop, target,
                      int((day + pd.Timedelta(hours=self.EXIT_H) - now).total_seconds() // 60),
                      ["liquidity_sweep_reclaim", f"level={key}", f"pierce={pierce:.2f}atr"],
                      {"swept_level": lvl, "level_name": key, "sweep_extreme": extreme,
                       "pierce_atr": pierce, "sl_dist": abs(entry - stop),
                       "pre_range": atr, "spread": ask - bid, "minutes_since_entry": 0})


BOTS = [GoldBreakout0630(), IndexBreakoutUSOpen(), SP500LondonBreakout(),
        GoldNYBreakout(), EURUSDLondonBreakout(), VWAPReversion(),
        H4PullbackContinuation(), LiquiditySweepReclaim()]

# BOT_I — RETIRED BEFORE DEPLOYMENT, on evidence. 2 years of XAUUSD, one configuration:
#   519 sessions -> 221 reached sweep+rejection (42.6%) -> 15 trades = 7.3 per year
#   expectancy +0.144R, t +0.50; 237 trades needed for t>2 = 32.5 YEARS live
# The seven-condition conjunction is not wrong, it is unfalsifiable on any horizon that
# matters. A shadow producing ~7 observations a year reports INSUFFICIENT_EVIDENCE forever,
# and a desk that carries it is larger without being better.
# The class is kept in bot_i.py: the finding is about frequency, not about the idea, and the
# funnel (where 221 becomes 15) is the useful record.


# ==================================================================== execution
def demo_gate(acct) -> str | None:
    """Hard gate. Returns a reason to HALT, or None to proceed."""
    lg = sv = None
    for line in (ROOT / "config" / "guardian.env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("ACCOUNT_LOGIN"):
            lg = int(s.split("=", 1)[1].strip())
        elif s.startswith("ACCOUNT_SERVER_CONTAINS"):
            sv = s.split("=", 1)[1].strip().upper()
    if lg is None or not sv:
        return "guardian.env has no ACCOUNT_LOGIN / ACCOUNT_SERVER_CONTAINS"
    if int(acct.login) != lg or sv not in str(acct.server).upper():
        return f"WRONG ACCOUNT: bound {lg}/~{sv}, connected {acct.login}/{acct.server}"
    if acct.trade_mode != 0:
        return f"NOT A DEMO ACCOUNT (trade_mode={acct.trade_mode}). Demo only."
    return None


def intent_id(login, sid, symbol, side, volume, ts) -> str:
    raw = f"{login}|{sid}|{symbol}|{side}|{volume:.2f}|{ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cmd_status():
    trades = load_trades()
    print("=" * 84)
    print(" FTMO CHALLENGE CONTROLLER — status")
    print("=" * 84)
    print(f"  total demo trades logged: {len(trades)}")
    print(f"\n  {'bot':<28}{'stage':<18}{'n':>5}{'expR':>9}{'PF':>7}{'P(pass)':>9}{'P(brch)':>9}")
    for b in BOTS:
        st = bot_stats(b.strategy_id)
        po = posterior(st, b.prior_expectancy_R, b.prior_n)
        sd = st.get("sd_R", 1.0) if st.get("n", 0) > 1 else 1.0
        pp = p_pass_estimate(po["exp"], sd, RISK_EXPERIMENTAL) if st.get("n", 0) else \
             {"p_pass": float("nan"), "p_breach": float("nan")}
        print(f"  {b.strategy_id:<28}{b.stage:<18}{st.get('n',0):>5}"
              f"{po['exp']:>+9.3f}{st.get('pf',float('nan')):>7.2f}"
              f"{pp['p_pass']:>9.1%}" if pp["p_pass"] == pp["p_pass"] else
              f"  {b.strategy_id:<28}{b.stage:<18}{st.get('n',0):>5}"
              f"{po['exp']:>+9.3f}{'--':>7}{'--':>9}{'--':>9}  (prior only)")
    print(f"\n  epoch review every {EPOCH_TRADES} closed trades. "
          f"Next at {((len(trades)//EPOCH_TRADES)+1)*EPOCH_TRADES}.")
    print(f"  risk: {RISK_EXPERIMENTAL:.2%} experimental, {RISK_ESTABLISHED:.2%} established, "
          f"{MAX_CONCURRENT_RISK:.2%} concurrent cap")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live-demo", action="store_true")
    a = ap.parse_args()
    if a.status or not (a.dry_run or a.live_demo):
        cmd_status(); return

    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit("MetaTrader5 required -- run on the VPS")
    import pandas as pd
    if not mt5.initialize():
        sys.exit(f"initialize failed: {mt5.last_error()}")
    acct = mt5.account_info()
    if acct is None:
        mt5.shutdown(); sys.exit("HALT: not logged in")
    why = demo_gate(acct)
    if why:
        mt5.shutdown(); sys.exit(f"HALT: {why}")
    print(f"DEMO GATE OK -> {acct.login} {acct.server} equity {acct.equity:.2f}")

    term = mt5.terminal_info()
    if term is not None and not term.trade_allowed and not a.dry_run:
        sys.exit("HALT: AlgoTrading is DISABLED in the MT5 terminal (retcode 10027 for every "
                 "order). This is a terminal toggle, not a bot fault -- enable it via the "
                 "AlgoTrading button and Tools > Options > Expert Advisors > 'Allow "
                 "algorithmic trading'. Halting so no bot burns its daily attempts.")
    if a.dry_run:
        print("DRY RUN: intents will be printed, nothing sent.\n")

    trades_pf = load_trades()
    problems = preflight(mt5, acct, trades_pf)
    if problems:
        print("\nPREFLIGHT FAILED -- DESK FAULT, NOT TRADING:")
        for p in problems:
            print(f"  x {p}")
        print("  A failed instrumentation check is not a market veto. Fix the desk.")
        mt5.shutdown(); sys.exit(1)
    print("PREFLIGHT OK -- account, clock, data, state, ledgers all verified")

    if not a.dry_run:
        time_exits(mt5, acct, BOTS, dry_run=False)
        nc = reconcile(mt5)
        if nc:
            print(f"RECONCILED {nc} closed position(s)")

    try:                                   # the Brain ingests before the desk decides
        from trading_brain import learn
        n = learn()
        if n:
            print(f"BRAIN: learned from {n} newly closed trade(s)")
    except Exception as e:
        print(f"BRAIN: unavailable ({e}) -- trading continues on priors")

    trades = load_trades()
    # A FILLED trade closes the session for that bot. A REJECTED order does not -- it is a
    # broker problem, not a trade, and letting it lock the bot out silently loses the whole
    # day's evidence. Rejections are capped instead, so a persistent error cannot spam orders.
    london_today = pd.Timestamp.now(tz="Europe/London").date().isoformat()
    traded_today, attempts_today = {}, {}
    for t in trades:
        if t.get("kind") == "close" or not t.get("timestamp", "").startswith(london_today):
            continue
        sid = t["strategy_id"]
        # 10027 = AutoTrading disabled: a TERMINAL condition affecting every bot equally.
        # Counting it against one bot's 3 attempts loses that bot the day for something it
        # did not do, and something no bot could have avoided.
        if t.get("retcode") != 10027:
            attempts_today[sid] = attempts_today.get(sid, 0) + 1
        if t.get("ticket"):
            traded_today[sid] = True
    for sid, n in attempts_today.items():
        if n >= MAX_ORDER_ATTEMPTS_PER_DAY and sid not in traded_today:
            traded_today[sid] = True
            print(f"  {sid}: BLOCKED -- {n} rejected orders today, not retrying")

    st_ = ChallengeState(**challenge_anchors(acct, trades))
    st = st_
    print(f"profit {st.profit_pct:+.2%}  daily headroom {st.daily_headroom:.2%}  "
          f"total headroom {st.total_headroom:.2%}  trading days {st.trading_days}\n")

    import market_state as MS, macro_context as MC, desk as DESK
    desk_now = MS.broker_now_london(mt5)          # ONE clock, read once per cycle
    print(f"  DESK CLOCK {desk_now:%Y-%m-%d %H:%M} London (broker)")
    opp_by_symbol, states = {}, {}
    for sym in sorted({b.symbol for b in BOTS}):
        if not mt5.symbol_select(sym, True):
            continue
        tk = mt5.symbol_info_tick(sym)
        if tk is None:
            continue
        st = MS.compute(mt5, sym, desk_now, tk.ask, tk.ask - tk.bid)
        st.update(MC.compute(mt5, sym, desk_now))
        states[sym] = st
        opp_by_symbol[sym] = DESK.classify_opportunity(st)
        print(f"  MARKET {sym:<12}{','.join(opp_by_symbol[sym]['opportunities'])}")

    try:
        from trading_brain import belief as _bel
        beliefs = {b.strategy_id: _bel(b.strategy_id, b.prior_expectancy_R, b.prior_n)
                   for b in BOTS}
    except Exception:
        beliefs = {}
    plan = DESK.allocate(BOTS, opp_by_symbol, lambda b: risk_for(b, st_), st_,
                         beliefs=beliefs)
    print(f"\n  CIO: {sum(1 for d in plan['decisions'].values() if d['allow'])} "
          f"of {len(BOTS)} funded, {plan['total_risk']:.3%} total risk")

    for bot in BOTS:
        d = plan["decisions"].get(bot.strategy_id, {})
        if not d.get("allow"):
            print(f"  {bot.strategy_id}: NOT FUNDED -- {d.get('reason','no decision')}")
            continue
        if not mt5.symbol_select(bot.symbol, True):
            print(f"  {bot.strategy_id}: symbol_select failed"); continue
        tick = mt5.symbol_info_tick(bot.symbol)
        r = mt5.copy_rates_from_pos(bot.symbol, mt5.TIMEFRAME_M1, 0, 600)
        if r is None or not len(r):
            print(f"  {bot.strategy_id}: no M1 data"); continue
        m1 = pd.DataFrame(r)
        import market_state as _MS
        m1.index = _MS.to_london(m1["time"], _MS.broker_utc_offset(mt5, bot.symbol))
        d1 = trend_context(mt5, bot.symbol, tick.ask)
        # ONE clock for the whole desk: the broker's. Using m1.index[-1] gave each symbol its
        # own "now", so a closed market evaluated its window against an hour-old timestamp.
        ctx = {"now_london": desk_now, "m1": m1,
               "bid": tick.bid, "ask": tick.ask, "traded_today": traded_today, "d1": d1}

        blackout = in_event_blackout(ctx["now_london"])
        if blackout:
            print(f"  {bot.strategy_id}: no trade -- {blackout}"); continue

        ctx["state"] = states.get(bot.symbol, {})
        sig = bot.generate_signal(ctx)
        if sig is None:
            print(f"  {bot.strategy_id}: no trade -- "
                  f"{getattr(bot, 'no_signal_reason', 'unspecified')}"); continue

        import market_state as MS, macro_context as MC, shadows as SH
        sess = ctx["now_london"].normalize() + pd.Timedelta(
            hours=getattr(bot, "ENTRY_H", getattr(bot, "SESSION_H", 8)),
            minutes=getattr(bot, "ENTRY_M", getattr(bot, "SESSION_M", 0)))
        lvl = next((float(r.split("=")[1]) for r in (sig.reason_codes or [])
                    if r.startswith("level=")), None)
        state = MS.compute(mt5, bot.symbol, ctx["now_london"], sig.entry_price,
                           ctx["ask"] - ctx["bid"], session_start=sess,
                           level=lvl, side=sig.side,
                           vwap=sig.feature_snapshot.get("vwap"),
                           sigma=sig.feature_snapshot.get("sigma"))
        state.update(MC.compute(mt5, bot.symbol, ctx["now_london"]))
        sig.feature_snapshot.update({f"d1_{k}": v for k, v in d1.items()})

        geo = stop_geometry(sig, state, info=None, spread=ctx["ask"] - ctx["bid"])
        sig.feature_snapshot["stop_geometry"] = geo
        if not geo["ok"]:
            print(f"  {bot.strategy_id}: SIGNAL but stop rejected -- {geo['reason']}")
            continue
        if geo.get("widened_to"):
            print(f"  {bot.strategy_id}: stop widened {sig.risk_distance():.2f} -> "
                  f"{geo['widened_to']:.2f} ({geo['reason']}); volume reduced to hold "
                  f"dollar risk constant")
            sig.stop_price = sig.entry_price - sig.side * geo["widened_to"]

        risk = plan["decisions"][bot.strategy_id]["risk"]
        veto = st.veto(risk)
        if veto:
            print(f"  {bot.strategy_id}: SIGNAL but VETOED -- {veto}"); continue

        info = mt5.symbol_info(bot.symbol)
        money = st.equity * risk
        per_lot = sig.risk_distance() * (info.trade_tick_value / info.trade_tick_size)
        vol = max(info.volume_min,
                  round(money / per_lot / info.volume_step) * info.volume_step)
        contract = info.trade_contract_size or 1
        notional = vol * contract * sig.entry_price
        if notional > MAX_NOTIONAL_MULT * st.equity:
            capped = (MAX_NOTIONAL_MULT * st.equity) / (contract * sig.entry_price)
            capped = int(capped / info.volume_step) * info.volume_step
            print(f"  {bot.strategy_id}: notional {notional:,.0f} > "
                  f"{MAX_NOTIONAL_MULT}x equity -- volume {vol} -> {capped}")
            vol = capped
        if vol < info.volume_min:
            print(f"  {bot.strategy_id}: SIGNAL but volume {vol} below min "
                  f"{info.volume_min} after caps -- skipped"); continue
        iid = intent_id(acct.login, bot.strategy_id, bot.symbol, sig.side, vol, sig.timestamp)
        print(f"  {bot.strategy_id}: SIGNAL side={sig.side:+d} entry={sig.entry_price:.2f} "
              f"sl={sig.stop_price:.2f} tp={sig.target_price:.2f} risk={risk:.3%} "
              f"vol={vol} intent={iid}")

        missing = [k for k in MANDATORY_STATE if state.get(k) in (None, "")]
        if missing:
            print(f"  {bot.strategy_id}: DATA_INTEGRITY -- not sending. Missing "
                  f"{', '.join(missing)} (d1_bars={state.get('d1_bars')}, "
                  f"ms_error={state.get('ms_error')}). A NULL regime is not 'neutral', and a "
                  f"trade the desk cannot learn from is not worth the risk.")
            continue

        shadow_verdicts = SH.evaluate(bot.strategy_id, state, sig.side, sig.risk_distance())

        pre = {"intent_id": iid, "strategy_id": bot.strategy_id,
               "market_state": state, "shadows": shadow_verdicts,
               "strategy_version": bot.strategy_version, "timestamp": sig.timestamp,
               "symbol": bot.symbol, "side": sig.side, "entry": sig.entry_price,
               "stop": sig.stop_price, "target": sig.target_price, "risk_pct": risk,
               "volume": vol, "account_equity": st.equity,
               "daily_loss_headroom": st.daily_headroom, "total_loss_headroom": st.total_headroom,
               "spread": ctx["ask"] - ctx["bid"], "reason_codes": sig.reason_codes,
               "feature_snapshot": sig.feature_snapshot, "R": None, "outcome": None}

        if bot.shadow:
            pre["shadow_only"] = True
            pre["retcode"] = None
            pre["ticket"] = None
            append_trade(pre)
            print(f"     SHADOW ONLY -- recorded, no order sent "
                  f"(promote the bot to trade it)")
            continue

        if a.dry_run:
            print(f"     DRY RUN -- not sent"); continue

        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": bot.symbol, "volume": float(vol),
               "type": mt5.ORDER_TYPE_BUY if sig.side > 0 else mt5.ORDER_TYPE_SELL,
               "price": ctx["ask"] if sig.side > 0 else ctx["bid"],
               "sl": float(sig.stop_price), "tp": float(sig.target_price),
               "deviation": 20, "magic": 990001, "comment": iid[:16],
               "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
        res = mt5.order_send(req)
        rc = getattr(res, "retcode", None)
        pre["retcode"] = rc
        pre["fill"] = getattr(res, "price", None)
        pre["actual_slippage"] = (abs(pre["fill"] - sig.entry_price)
                                  if pre.get("fill") else None)
        pre["ticket"] = getattr(res, "order", None) or getattr(res, "deal", None)
        if rc == mt5.TRADE_RETCODE_DONE and not pre["ticket"]:
            match = [p for p in (mt5.positions_get(symbol=bot.symbol) or [])
                     if p.magic == 990001 and p.comment == iid[:16]]
            pre["ticket"] = match[0].ticket if match else None
        append_trade(pre)
        print(f"     order_send -> {rc} fill={pre['fill']}")
        if rc == mt5.TRADE_RETCODE_DONE:
            pos = [p for p in (mt5.positions_get(symbol=bot.symbol) or []) if p.magic == 990001]
            ok = any(abs(p.sl - sig.stop_price) < 1e-6 for p in pos)
            print(f"     broker stop verified: {ok}")
            if not ok:
                print("     !! STOP NOT ON BROKER -- manual review required")
    mt5.shutdown()


if __name__ == "__main__":
    main()
