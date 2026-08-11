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

# ---- promotion ladder
STAGES = ("IDEA", "BACKTESTED", "VALIDATED", "DEMO_CANDIDATE", "DEMO_PROVEN",
          "CHALLENGE_CANDIDATE", "RETIRED")
DEMO_PROVEN_MIN_TRADES = 40


# ==================================================================== bot interface
@dataclass
class Signal:
    strategy_id: str
    strategy_version: str
    timestamp: str
    symbol: str
    side: int                      # +1 long, -1 short
    entry_type: str                # "stop" | "market" | "limit"
    entry_price: float
    stop_price: float
    target_price: float
    expected_holding_minutes: int
    reason_codes: list = field(default_factory=list)
    feature_snapshot: dict = field(default_factory=dict)

    def risk_distance(self) -> float:
        return abs(self.entry_price - self.stop_price)


class Bot:
    """Every candidate implements this. A bot NEVER sends an order."""
    strategy_id = "base"
    strategy_version = "0"
    symbol = ""
    stage = "IDEA"
    prior_expectancy_R = 0.0        # from backtest -- a PRIOR, not a promise
    prior_n = 0

    def generate_signal(self, ctx) -> Signal | None:
        raise NotImplementedError

    def manage_position(self, position, ctx) -> str:
        """Return "hold" or "close". Default: broker stop/target does the work."""
        return "hold"


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


def risk_for(bot: Bot, st: ChallengeState) -> float:
    """LOSS_AWARE + TARGET_AWARE. Predeclared. Never increases after a loss."""
    base = RISK_ESTABLISHED if bot.stage in ("DEMO_PROVEN", "CHALLENGE_CANDIDATE") \
        else RISK_EXPERIMENTAL
    # taper as either boundary approaches, and as the target comes into reach
    hd = max(st.daily_headroom / MAX_DAILY_LOSS_PCT, 0.0)
    ht = max(st.total_headroom / MAX_TOTAL_LOSS_PCT, 0.0)
    taper = min(1.0, hd, ht)
    if st.profit_remaining < 0.02:            # within 2% of target: protect the pass
        taper = min(taper, 0.5)
    return round(base * taper, 6)


# ==================================================================== ledger
def append_trade(rec: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    with TRADES.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def load_trades() -> list:
    if not TRADES.exists():
        return []
    return [json.loads(l) for l in TRADES.read_text().splitlines() if l.strip()]


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


# ==================================================================== BOT_A
class GoldBreakout0630(Bot):
    """BOT_A. Frozen spec: intraday-lab/gold0630/GOLD_BREAKOUT_FROZEN.md

    Breakout of the 90-minute pre-06:30-London range. TP $60 / SL $30. Flat by 16:00 London,
    so it pays ZERO overnight financing -- which is what killed the frozen portfolio.

    PRIOR from backtest: +0.39R over 60 days, t=+2.42, BUT chosen as best of 14 configurations,
    so the honest prior shrinks it. prior_n is deliberately small: this prior is weak and live
    evidence should dominate quickly.
    """
    strategy_id = "BOT_A_gold_0630_breakout"
    strategy_version = "1.0.0"
    symbol = "XAUUSD"
    stage = "DEMO_CANDIDATE"
    prior_expectancy_R = 0.15        # shrunk from +0.39 for best-of-14 selection
    prior_n = 30

    TP, SL, PRE_MIN = 60.0, 30.0, 90
    ENTRY_H, ENTRY_M, EXIT_H, EXIT_M = 6, 30, 16, 0

    def generate_signal(self, ctx) -> Signal | None:
        import pandas as pd
        now = ctx["now_london"]
        bars = ctx["m1"]                       # DataFrame indexed in Europe/London
        if bars is None or len(bars) < self.PRE_MIN + 5:
            return None
        day = now.normalize()
        t0 = day + pd.Timedelta(hours=self.ENTRY_H, minutes=self.ENTRY_M)
        cut = day + pd.Timedelta(hours=self.EXIT_H, minutes=self.EXIT_M)
        if not (t0 <= now < cut):
            return None
        if ctx.get("traded_today", {}).get(self.strategy_id):
            return None
        pre = bars[(bars.index >= t0 - pd.Timedelta(minutes=self.PRE_MIN)) & (bars.index < t0)]
        if len(pre) < 30:
            return None
        hi, lo = float(pre["high"].max()), float(pre["low"].min())
        bid, ask = ctx["bid"], ctx["ask"]
        if ask >= hi:
            side, lvl = 1, hi
        elif bid <= lo:
            side, lvl = -1, lo
        else:
            return None
        entry = ask if side > 0 else bid
        return Signal(self.strategy_id, self.strategy_version, now.isoformat(), self.symbol,
                      side, "market", entry, entry - side * self.SL, entry + side * self.TP,
                      int((cut - now).total_seconds() // 60),
                      ["pre_range_break", f"level={lvl:.2f}"],
                      {"pre_high": hi, "pre_low": lo, "pre_range": hi - lo,
                       "spread": ask - bid, "minutes_since_0630": int((now - t0).total_seconds()//60)})


BOTS = [GoldBreakout0630()]


# ==================================================================== execution
def demo_gate(acct) -> str | None:
    """Hard gate. Returns a reason to HALT, or None to proceed."""
    lg = sv = None
    for line in (ROOT / "config" / "guardian.env").read_text().splitlines():
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
    if a.dry_run:
        print("DRY RUN: intents will be printed, nothing sent.\n")

    trades = load_trades()
    traded_today = {}
    today = datetime.now(timezone.utc).date().isoformat()
    for t in trades:
        if t.get("timestamp", "").startswith(today):
            traded_today[t["strategy_id"]] = True

    st = ChallengeState(equity=acct.equity, balance=acct.balance,
                        starting_balance=float(acct.balance), day_start_equity=float(acct.equity),
                        trading_days=len({t.get("timestamp","")[:10] for t in trades}),
                        open_risk_pct=0.0)
    print(f"profit {st.profit_pct:+.2%}  daily headroom {st.daily_headroom:.2%}  "
          f"total headroom {st.total_headroom:.2%}  trading days {st.trading_days}\n")

    for bot in BOTS:
        if not mt5.symbol_select(bot.symbol, True):
            print(f"  {bot.strategy_id}: symbol_select failed"); continue
        tick = mt5.symbol_info_tick(bot.symbol)
        r = mt5.copy_rates_from_pos(bot.symbol, mt5.TIMEFRAME_M1, 0, 600)
        if r is None or not len(r):
            print(f"  {bot.strategy_id}: no M1 data"); continue
        m1 = pd.DataFrame(r)
        m1.index = pd.to_datetime(m1["time"], unit="s", utc=True).dt.tz_convert("Europe/London")
        ctx = {"now_london": m1.index[-1], "m1": m1, "bid": tick.bid, "ask": tick.ask,
               "traded_today": traded_today}
        sig = bot.generate_signal(ctx)
        if sig is None:
            print(f"  {bot.strategy_id}: NO SIGNAL"); continue

        risk = risk_for(bot, st)
        veto = st.veto(risk)
        if veto:
            print(f"  {bot.strategy_id}: SIGNAL but VETOED -- {veto}"); continue

        info = mt5.symbol_info(bot.symbol)
        money = st.equity * risk
        per_lot = sig.risk_distance() * (info.trade_tick_value / info.trade_tick_size)
        vol = max(info.volume_min,
                  round(money / per_lot / info.volume_step) * info.volume_step)
        iid = intent_id(acct.login, bot.strategy_id, bot.symbol, sig.side, vol, sig.timestamp)
        print(f"  {bot.strategy_id}: SIGNAL side={sig.side:+d} entry={sig.entry_price:.2f} "
              f"sl={sig.stop_price:.2f} tp={sig.target_price:.2f} risk={risk:.3%} "
              f"vol={vol} intent={iid}")

        pre = {"intent_id": iid, "strategy_id": bot.strategy_id,
               "strategy_version": bot.strategy_version, "timestamp": sig.timestamp,
               "symbol": bot.symbol, "side": sig.side, "entry": sig.entry_price,
               "stop": sig.stop_price, "target": sig.target_price, "risk_pct": risk,
               "volume": vol, "account_equity": st.equity,
               "daily_loss_headroom": st.daily_headroom, "total_loss_headroom": st.total_headroom,
               "spread": ctx["ask"] - ctx["bid"], "reason_codes": sig.reason_codes,
               "feature_snapshot": sig.feature_snapshot, "R": None, "outcome": None}

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
