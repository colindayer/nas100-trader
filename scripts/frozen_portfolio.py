"""FROZEN PORTFOLIO — the autonomous rebalance loop for the production strategy.

    py scripts\\frozen_portfolio.py --dry-run       # compute and PRINT the full order plan, send nothing
    py scripts\\frozen_portfolio.py --live          # execute (DEMO accounts only, all gates enforced)

THE FROZEN STRATEGY (fixed; this file may not deviate from it)
    universe    GOLD SILVER OIL COPPER NAS100 SP500        six only, no FX, no CARRY
    signal      portfolio_mt5.target_weights(sleeves=('TREND',)), 252-day lookback
    sizing      5% annualised vol target, max_leverage 3.0
    execution   daily rebalance, 0.005 no-trade band
    exit        target-weight REDUCTION, ZERO, or SIGN REVERSAL only
    safeguard   15% catastrophe stop, broker-side, disaster protection ONLY
    reference   Sharpe 0.653, maxDD -10.19%, ~84% pass, ~5.5% breach, ~438 median days

    There is NO fixed take-profit and NO performance trailing stop. Four separate studies
    (fixed TP/SL, catastrophe, ATR trailing, structure trailing) failed to beat holding the
    target weight, and the one that appeared to win collapsed from Sharpe 1.13 to 0.01 under a
    gap-aware fill. Adding one here would silently trade a different, untested strategy.

HELD STATE COMES FROM THE BROKER, NEVER FROM RECOMPUTED HISTORY
    The no-trade band is path-dependent: rebuilding it from 504 days of warm-up still leaves a
    5.1e-04 weight error (tests/test_frozen_parity.py). So `held` is derived from ACTUAL broker
    positions every run. A restart therefore self-heals, and the bot and the broker cannot
    silently disagree.

IDEMPOTENCY
    Every intent carries a deterministic id: sha1(account, symbol, side, rounded volume, UTC
    date, magic). The ledger is consulted BEFORE submission; an id already present today is
    skipped. Restarting the process mid-run therefore cannot duplicate an order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time as _t
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

from scripts.portfolio_mt5 import (MAGIC, SYMBOL_MAP, fetch_daily, notional_per_lot,
                                   resolve_symbols, target_weights, _notify)

FROZEN_UNIVERSE = ["GOLD", "SILVER", "OIL", "COPPER", "NAS100", "SP500"]
FROZEN_VOL, FROZEN_LEV, FROZEN_BAND = 0.05, 3.0, 0.005
CATASTROPHE = 0.15                     # broker-side disaster stop, from entry
STRATEGY_ID = "portfolio_frozen_v1"
PLAN_PATH = ROOT / "registry" / "frozen_plan.json"
FILLS_PATH = ROOT / "registry" / "frozen_fills.jsonl"
AUDIT_FIRST_N = 5                      # the first five fills are auto-audited and summarised


def _now():
    return datetime.now(timezone.utc).isoformat()


def intent_id(login, symbol, side, volume, magic=MAGIC):
    """Deterministic per account+symbol+side+size+UTC DAY. Two runs on the same day that would
    place the same order produce the same id, so the ledger can refuse the duplicate."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = f"{login}|{symbol}|{side}|{volume:.2f}|{day}|{magic}"
    return "FZ-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def held_weights(syms: dict, equity: float) -> dict:
    """Current exposure per internal name as a FRACTION OF EQUITY, signed, from broker truth."""
    inv = {v: k for k, v in syms.items()}
    out = {k: 0.0 for k in syms}
    raw = mt5.positions_get()
    if raw is None:
        raise RuntimeError("positions_get() failed — cannot establish held state, refusing to act")
    for p in raw:
        if p.magic != MAGIC:
            continue
        name = inv.get(p.symbol)
        if name is None:
            continue
        info, tick = mt5.symbol_info(p.symbol), mt5.symbol_info_tick(p.symbol)
        npl = notional_per_lot(p.symbol, info, tick)
        signed = p.volume if p.type == mt5.ORDER_TYPE_BUY else -p.volume
        out[name] += signed * npl / max(equity, 1e-9)
    return out


def our_positions(symbol: str):
    raw = mt5.positions_get(symbol=symbol)
    if raw is None:
        raise RuntimeError(f"positions_get({symbol}) failed — refusing to act")
    return [p for p in raw if p.magic == MAGIC]


def build_plan(acct, syms, w_target, held, equity):
    """Return the ordered action list. Pure computation: touches no broker state."""
    plan = []
    for name in FROZEN_UNIVERSE:
        if name not in syms:
            plan.append(dict(name=name, action="SKIP", reason="symbol unresolved"))
            continue
        sym = syms[name]
        tgt = float(w_target.get(name, 0.0))
        cur = float(held.get(name, 0.0))
        delta_w = tgt - cur
        if abs(delta_w) <= FROZEN_BAND:
            plan.append(dict(name=name, symbol=sym, action="HOLD", target_w=tgt, held_w=cur,
                             delta_w=delta_w, reason=f"|delta| {abs(delta_w):.4f} <= band {FROZEN_BAND}"))
            continue
        info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            plan.append(dict(name=name, symbol=sym, action="SKIP", reason="no symbol info/tick"))
            continue
        npl = notional_per_lot(sym, info, tick)
        step = info.volume_step or 0.01
        lots = abs(delta_w) * equity / max(npl, 1e-9)
        lots = float(max(info.volume_min, round(lots / step) * step))
        lots = float(min(lots, info.volume_max or 100.0))
        crosses_zero = (tgt == 0.0) or (cur != 0.0 and np.sign(tgt) != np.sign(cur) and tgt != 0)
        act = ("REDUCE_OR_CLOSE" if (abs(tgt) < abs(cur) or crosses_zero) else "OPEN_OR_INCREASE")
        side = "BUY" if delta_w > 0 else "SELL"
        plan.append(dict(name=name, symbol=sym, action=act, side=side, target_w=tgt, held_w=cur,
                         delta_w=delta_w, volume=lots, price=(tick.ask if side == "BUY" else tick.bid),
                         spread=float(tick.ask - tick.bid), notional_per_lot=npl,
                         crosses_zero=bool(crosses_zero),
                         intent_id=intent_id(acct.login, sym, side, lots)))
    # closes/reductions execute BEFORE opens: frees margin and cannot be blocked by new exposure
    order = {"REDUCE_OR_CLOSE": 0, "OPEN_OR_INCREASE": 1, "HOLD": 2, "SKIP": 3}
    return sorted(plan, key=lambda p: order.get(p["action"], 9))


def catastrophe_stop(entry: float, side: str, info) -> float:
    """15% from entry, broker-side. Rounded so the DISTANCE never exceeds 15%: the gate blocks
    anything beyond that as implausible (it was written after the BTC naked-stop failure), and a
    tick rounded the wrong way would trip it."""
    raw = entry * (1 - CATASTROPHE) if side == "BUY" else entry * (1 + CATASTROPHE)
    digits = int(getattr(info, "digits", 5) or 5)
    lvl = round(raw, digits)
    if side == "BUY" and (entry - lvl) / entry > CATASTROPHE:
        lvl = round(lvl + 10 ** (-digits), digits)
    if side == "SELL" and (lvl - entry) / entry > CATASTROPHE:
        lvl = round(lvl - 10 ** (-digits), digits)
    # respect the broker's minimum stop distance
    pt = float(getattr(info, "point", 0.0) or 0.0)
    min_dist = (getattr(info, "trade_stops_level", 0) or 0) * pt
    if min_dist:
        lvl = min(lvl, entry - min_dist) if side == "BUY" else max(lvl, entry + min_dist)
    return float(lvl)


# Retcodes that prove the order was rejected BEFORE reaching the market. Only these are safe to
# retry: nothing was executed, so a repeat cannot duplicate a position. Every other outcome --
# including a timeout, an exception, or an unrecognised code -- is treated as POSSIBLY FILLED and
# blocks the retry, because "we do not know" must never mean "try again".
PRE_TRADE_REJECTIONS = {
    10026,   # SERVER_DISABLES_AT   - broker forbids EAs
    10027,   # CLIENT_DISABLES_AT   - AlgoTrading button off in this terminal
    10018,   # MARKET_CLOSED
    10014,   # INVALID_VOLUME
    10016,   # INVALID_STOPS
    10019,   # NO_MONEY
    10030,   # UNSUPPORTED_FILLING_MODE
}


def already_submitted_today(iid: str) -> bool:
    """Idempotency: consulted BEFORE submission, so a restart mid-run cannot duplicate an order.

    A PRE-TRADE rejection does not count as submitted. All six orders were rejected 10027 on
    2026-08-03 and were still written to the fills ledger; without this exemption the retry after
    switching AlgoTrading on would have been silently skipped for the rest of the day."""
    if not FILLS_PATH.exists():
        return False
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for line in FILLS_PATH.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            return True                       # unparseable ledger line -> fail closed
        if r.get("intent_id") == iid and str(r.get("ts", "")).startswith(day):
            if r.get("retcode") in PRE_TRADE_REJECTIONS:
                continue                      # never reached the market; safe to retry
            return True
    return False


def submit_plan(acct, plan, syms, equity, guardian_detail):
    """Execute the plan. Ledger BEFORE submit, broker-side stop WITH the order, verification and
    reconciliation AFTER. Nothing here decides what to trade -- build_plan already did."""
    from execution_safety.execution_guard import armed
    from execution_safety.gate import Signal, authorize
    from execution_safety.position_ledger import PositionLedger
    from execution_safety.startup_reconciler import reconcile
    from execution_safety.strategy_contract import StrategyRegistry
    from execution_safety import safety_state as ss

    reg, ledger = StrategyRegistry(), PositionLedger()
    contract = reg.get(STRATEGY_ID)
    if contract is None or not contract.verify():
        _notify("critical_error", f"{STRATEGY_ID}: contract missing or signature invalid")
        raise SystemExit("strategy contract missing or unsigned — refusing to trade")

    submitted, results = 0, []
    for p in plan:
        if p["action"] not in ("REDUCE_OR_CLOSE", "OPEN_OR_INCREASE"):
            continue
        sym, side, vol = p["symbol"], p["side"], float(p["volume"])
        iid = p["intent_id"]
        if already_submitted_today(iid):
            print(f"  SKIP {sym}: intent {iid} already submitted today (idempotent)")
            continue

        info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
        price = float(tick.ask if side == "BUY" else tick.bid)
        sl = catastrophe_stop(price, side, info)

        sig = Signal(signal_id=iid, strategy_id=STRATEGY_ID, strategy_version="v1",
                     symbol=sym, direction=1 if side == "BUY" else -1,
                     entry=price, stop_loss=sl)
        open_now = [{"symbol": q.symbol} for q in (mt5.positions_get() or [])
                    if q.magic == MAGIC]
        dec = authorize(sig, registry=reg, inference=lambda s: "ALLOW_PAPER",
                        guardian_ok=True, equity=equity, account_is_demo=True,
                        open_positions=open_now, shadow=False)
        if dec["decision"] != "ALLOW_PAPER":
            print(f"  BLOCKED {sym}: {dec['reason_codes']}")
            _notify("guardian_block", f"{sym} BLOCKED {dec['reason_codes']}")
            results.append({"symbol": sym, "blocked": dec["reason_codes"]})
            continue

        # LEDGER FIRST -- an unledgered fill is an orphan by our own policy
        intent_ts = _now()
        try:
            dec["order_intent"]["calculated_volume"] = vol
            ledger.record_intent(dec["order_intent"], contract.approved_trial_ids,
                                 dec["decision_id"])
        except Exception as e:
            print(f"  BLOCKED {sym}: ledger unavailable ({type(e).__name__}) — not submitting")
            continue

        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": vol,
               "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
               "price": price, "sl": sl, "deviation": 20, "magic": MAGIC,
               # THE COMMENT MUST MATCH THE LEDGER ENTRY. position_ledger.is_ours() traces a
               # broker position back to the ledger BY COMMENT, and the gate writes
               # f"{strategy_id}:{version}". Sending our own string made the very position we had
               # just opened look like an ORPHAN_POSITION -- a CRITICAL finding -- which halted the
               # run after the first fill on 2026-08-03.
               "comment": dec["order_intent"]["comment"],
               "type_filling": mt5.ORDER_FILLING_IOC}
        t0 = _t.time()
        with armed(dec["decision_id"]):
            res = mt5.order_send(req)
        rc = getattr(res, "retcode", None)
        fill_px = float(getattr(res, "price", 0.0) or 0.0)
        latency_ms = (_t.time() - t0) * 1000.0

        # ---- POST-ORDER: verify the broker-side stop actually exists on the position
        ours = [q for q in (mt5.positions_get(symbol=sym) or []) if q.magic == MAGIC]
        pos = ours[-1] if ours else None
        stop_verified = bool(pos and pos.sl and pos.sl > 0)
        recon = reconcile(magic=MAGIC)
        rec = {"ts": _now(), "intent_id": iid, "intent_ts": intent_ts, "symbol": sym,
               "name": p["name"], "direction": side, "target_w": p["target_w"],
               "held_w": p["held_w"], "delta_w": p["delta_w"], "volume": vol,
               "requested_price": price, "fill_price": fill_px,
               "slippage": (fill_px - price) if fill_px else None,
               "spread": p.get("spread"), "catastrophe_stop": sl,
               "broker_stop": (float(pos.sl) if pos else None),
               "stop_verified": stop_verified, "magic": MAGIC, "retcode": rc,
               "latency_ms": round(latency_ms, 1), "decision_id": dec["decision_id"],
               "ledger_recorded": True, "reconciliation_ok": bool(recon.get("trading_allowed")),
               "account": acct.login, "server": acct.server}
        FILLS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FILLS_PATH, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        results.append(rec)

        if rc == 10009:
            submitted += 1
            try:
                ss.record_trade(iid)
            except ss.EnvelopeExhausted as e:
                # a halt raised mid-loop must stop the run cleanly, not crash it: the fill has
                # already happened and its record must still be written and reported
                print(f"  !! halted while recording {sym}: {e}")
                _notify("critical_error", f"FROZEN v1 halted after {sym} fill: {e}")
                break
            if not stop_verified:
                # a filled position with no broker-side stop is the BTC failure mode
                ss.halt("FILLED_WITHOUT_BROKER_STOP", path=ss.STATE_PATH)
                _notify("critical_error",
                        f"HALTED: {sym} filled with NO broker-side stop (ticket "
                        f"{getattr(pos,'ticket',None)})")
                print(f"  !! {sym} filled WITHOUT a broker stop — HALTED")
                break
            _notify("demo_fill", f"FROZEN v1 FILL {sym} {side} {vol}\n"
                                 f"px {fill_px} slip {rec['slippage']} stop {sl}\n"
                                 f"recon {'OK' if rec['reconciliation_ok'] else 'FAILED'}")
        else:
            print(f"  {sym} retcode {rc} — not filled")
    return submitted, results


def audit_fills():
    """Automatic audit of the first N fills, summarised for human review."""
    if not FILLS_PATH.exists():
        return
    rows = [json.loads(l) for l in FILLS_PATH.read_text().splitlines() if l.strip()]
    fills = [r for r in rows if r.get("retcode") == 10009][:AUDIT_FIRST_N]
    if not fills:
        return
    print("\n" + "=" * 100)
    print(f" AUTOMATIC FILL AUDIT — first {len(fills)} fill(s)")
    print("=" * 100)
    for i, r in enumerate(fills, 1):
        print(f" {i}. {r['name']} ({r['symbol']}) {r['direction']} {r['volume']}")
        print(f"    target_w {r['target_w']:+.4f}  held_w {r['held_w']:+.4f}  "
              f"delta_w {r['delta_w']:+.4f}")
        print(f"    requested {r['requested_price']}  filled {r['fill_price']}  "
              f"slippage {r['slippage']}  spread {r['spread']}")
        print(f"    catastrophe stop {r['catastrophe_stop']}  broker stop {r['broker_stop']}  "
              f"verified {r['stop_verified']}")
        print(f"    magic {r['magic']}  intent {r['intent_ts']}  fill {r['ts']}  "
              f"latency {r['latency_ms']}ms")
        print(f"    ledger {r['ledger_recorded']}  reconciliation "
              f"{'OK' if r['reconciliation_ok'] else 'FAILED'}  retcode {r['retcode']}")
    bad = [r for r in fills if not r["stop_verified"] or not r["reconciliation_ok"]]
    print("-" * 100)
    print(f" AUDIT: {len(fills)} fill(s), {len(bad)} with a failed stop or reconciliation")


def print_plan(acct, plan, diag, equity):
    print("=" * 100)
    print(f" FROZEN PORTFOLIO v1 — ORDER PLAN   {_now()}")
    print(f" account {acct.login} @ {acct.server}  equity {equity:,.2f}  "
          f"{'DEMO' if acct.trade_mode == 0 else '*** REAL ***'}")
    print(f" vol_target {FROZEN_VOL:.0%}  band {FROZEN_BAND}  scale {diag.get('scale')}  "
          f"realized_vol {diag.get('realized_vol', 0):.2%}  gross {diag.get('gross_exposure')}")
    print("=" * 100)
    hdr = (f"{'name':>7} {'action':>17} {'side':>5} {'target_w':>9} {'held_w':>8} {'delta_w':>8} "
           f"{'lots':>7} {'price':>11} {'spread':>8}")
    print(hdr)
    for p in plan:
        print(f"{p['name']:>7} {p['action']:>17} {p.get('side',''):>5} "
              f"{p.get('target_w',0):>9.4f} {p.get('held_w',0):>8.4f} {p.get('delta_w',0):>8.4f} "
              f"{p.get('volume',0):>7.2f} {p.get('price',0):>11.5f} {p.get('spread',0):>8.5f}"
              + (f"   {p.get('reason','')}" if p["action"] in ("HOLD", "SKIP") else ""))
    acts = [p for p in plan if p["action"] in ("REDUCE_OR_CLOSE", "OPEN_OR_INCREASE")]
    print("-" * 100)
    print(f" {len(acts)} order(s) to submit, {sum(1 for p in plan if p['action']=='HOLD')} hold, "
          f"{sum(1 for p in plan if p['action']=='SKIP')} skipped")
    return acts


def preflight(acct):
    """Every gate that must pass before a single order may be sent. Returns (ok, report)."""
    checks = {}
    checks["account_is_demo"] = (acct.trade_mode == 0)
    # account_info().trade_expert is the SERVER permission. It says nothing about the AlgoTrading
    # button in this terminal, which is what retcode 10027 (CLIENT_DISABLES_AT) reports. Preflight
    # said GO and all six orders were then rejected client-side. Both flags are required.
    checks["trade_expert_enabled"] = bool(getattr(acct, "trade_expert", False))
    checks["trade_allowed"] = bool(getattr(acct, "trade_allowed", False))
    try:
        _ti = mt5.terminal_info()
        checks["terminal_algotrading_on"] = bool(getattr(_ti, "trade_allowed", False))
        if not checks["terminal_algotrading_on"]:
            checks["_terminal_hint"] = ("the AlgoTrading button in this MT5 terminal is OFF -> "
                                        "every order returns 10027 CLIENT_DISABLES_AT")
    except Exception as e:
        checks["terminal_algotrading_on"] = False
        checks["_terminal_error"] = str(e)[:120]
    try:
        from execution_safety.startup_reconciler import reconcile
        r = reconcile(magic=MAGIC)
        checks["startup_reconciliation"] = bool(r.get("trading_allowed"))
    except Exception as e:
        checks["startup_reconciliation"] = False
        checks["_recon_error"] = str(e)[:120]
    try:
        from execution_safety import safety_state as ss
        st, _ = ss.load(login=acct.login)
        checks["not_halted"] = not st.halted
        checks["_halt_reason"] = st.halt_reason
    except Exception as e:
        checks["not_halted"] = False
        checks["_state_error"] = str(e)[:120]
    try:
        from execution_safety.guardian_bridge import guardian_ok
        g, det = guardian_ok(proposed_risk_pct=FROZEN_VOL / 10)
        checks["guardian_allows"] = bool(g)
        checks["_guardian"] = str(det)[:160]
    except Exception as e:
        checks["guardian_allows"] = False
        checks["_guardian_error"] = str(e)[:120]
    required = ["account_is_demo", "trade_expert_enabled", "trade_allowed",
                "terminal_algotrading_on", "startup_reconciliation", "not_halted",
                "guardian_allows"]
    return all(checks.get(k) for k in required), checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the plan, submit nothing")
    ap.add_argument("--live", action="store_true", help="execute (demo accounts only)")
    a = ap.parse_args()
    if not (a.dry_run or a.live):
        ap.error("choose --dry-run or --live")

    if mt5 is None or not mt5.initialize():
        raise SystemExit("MetaTrader5 unavailable — run on the VPS with the terminal open")
    acct = mt5.account_info()
    if acct is None:
        raise SystemExit("no account info")

    syms = {k: v for k, v in resolve_symbols(verbose=True).items() if k in FROZEN_UNIVERSE}
    missing = [k for k in FROZEN_UNIVERSE if k not in syms]
    px = fetch_daily(syms)[[k for k in FROZEN_UNIVERSE if k in syms]].dropna(how="any")
    w, diag = target_weights(px, carry_signs={}, target_vol=FROZEN_VOL,
                             max_leverage=FROZEN_LEV, sleeves=("TREND",))
    equity = float(acct.equity)
    held = held_weights(syms, equity)
    plan = build_plan(acct, syms, w, held, equity)

    ok, checks = preflight(acct)
    acts = print_plan(acct, plan, diag, equity)
    print("\n PREFLIGHT")
    for k, v in checks.items():
        if k.startswith("_"):
            print(f"   ({k[1:]}: {v})")
        else:
            print(f"   {'PASS' if v else 'FAIL'}  {k}")
    if missing:
        print(f"   FAIL  symbol_mapping — unresolved: {missing}")
        ok = False
    print(f"\n PREFLIGHT VERDICT: {'GO' if ok else 'NO-GO'}")

    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"ts": _now(), "account": acct.login, "server": acct.server, "equity": equity,
               "diag": diag, "plan": plan, "preflight": checks, "preflight_ok": ok,
               "frozen": {"universe": FROZEN_UNIVERSE, "vol": FROZEN_VOL, "band": FROZEN_BAND,
                          "catastrophe": CATASTROPHE, "sleeves": ["TREND"]}},
              open(PLAN_PATH, "w"), indent=1, default=str)
    print(f" plan written -> {PLAN_PATH}")

    if a.dry_run:
        audit_fills()
        print("\n DRY RUN — nothing submitted.")
        return
    if not ok:
        _notify("critical_error", f"FROZEN PORTFOLIO preflight NO-GO\n{checks}")
        raise SystemExit("preflight failed — no orders sent")
    n, _ = submit_plan(acct, plan, syms, equity, checks)
    print(f"\n SUBMITTED {n} order(s)")
    audit_fills()


if __name__ == "__main__":
    main()
