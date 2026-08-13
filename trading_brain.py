"""TRADING BRAIN — the layer above the controller. Experience becomes behaviour.

    py trading_brain.py --recall          what the Brain currently believes
    py trading_brain.py --learn           ingest closed trades, update beliefs, write lessons
    py trading_brain.py --weekly          the compounding step: rank, promote, retire, allocate

THE CONTROLLER IS NOW ONLY THE EXECUTION LAYER.
  controller  decides whether THIS signal becomes an order, right now
  brain       decides which bots exist, what they are worth, and how much each may risk

WHY THIS IS NOT A LOG
  A log is written and never read. The Brain is READ AT DECISION TIME: the controller calls
  recall() before sizing, and the allocation it gets back is the product of every trade that
  came before. If the Brain were deleted the desk would still trade -- but it would trade the
  same way in week 40 as in week 1. That is the difference.

APPEND-ONLY BY CONSTRUCTION
  events.jsonl is never rewritten. Beliefs are DERIVED from it on every read, so a belief can
  never drift away from the evidence that produced it, and any past decision can be replayed
  exactly as it was made. Hindsight cannot edit the record.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
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
BRAIN = ROOT / "data" / "brain"
EVENTS = BRAIN / "events.jsonl"                 # append-only, the only source of truth
TRADES = ROOT / "data" / "challenge" / "trades.jsonl"

EPOCH_TRADES = 20
RETIRE_MIN_TRADES = 25            # never retire on a small sample
RETIRE_T = -1.5                   # live t this bad, with enough n, retires a bot
PROMOTE_MIN_TRADES = 40
PROMOTE_T = 1.5


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(kind: str, **payload):
    """Append one immutable event. Nothing in this file ever rewrites events.jsonl."""
    BRAIN.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), "kind": kind, **payload}) + "\n")


def events(kind: str | None = None) -> list:
    if not EVENTS.exists():
        return []
    out = [json.loads(l) for l in EVENTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [e for e in out if kind is None or e["kind"] == kind]


def voided_intents() -> dict:
    """Trades whose EVIDENCE is void, with the reason. Nothing is deleted -- the ledger keeps
    every row forever. This only stops the Brain LEARNING from a trade that measured something
    other than what it claims to.

    Voiding is for provable instrumentation faults, never for losses. 'It lost' is evidence;
    'the clock was 3 hours off so this bot traded the Asian session while calling itself
    London' is not evidence about the London strategy.
    """
    out = {}
    for e in events("evidence_voided"):
        for iid in e.get("intent_ids", []):
            out[iid] = e.get("reason", "unspecified")
    return out


def closed_trades(include_voided=False) -> list:
    """Merge each pre-trade row with its close record. The ledger is append-only, so a
    completed trade is TWO rows sharing an intent_id -- the intent as it was decided, and
    the outcome as the broker reported it. Neither ever overwrites the other."""
    if not TRADES.exists():
        return []
    rows = [json.loads(l) for l in TRADES.read_text(encoding="utf-8").splitlines() if l.strip()]
    opens = {r["intent_id"]: r for r in rows if r.get("kind") != "close"}
    void = {} if include_voided else voided_intents()
    out = []
    for r in rows:
        if r.get("kind") != "close" or r.get("R") is None:
            continue
        if r["intent_id"] in void:
            continue
        merged = dict(opens.get(r["intent_id"], {}))
        merged.update(r)
        out.append(merged)
    return out


# ==================================================================== regime
def _medians(strategy_id: str) -> dict:
    """Per-bot scale. Absolute thresholds cannot work across instruments -- a $12 range is
    wide for gold and invisible on an index. Labels are relative to the bot's own history."""
    ts = [t for t in closed_trades() if t.get("strategy_id") == strategy_id]
    out = {}
    for key, get in (("pre_range", lambda t: (t.get("feature_snapshot") or {}).get("pre_range")),
                     ("spread", lambda t: t.get("spread"))):
        vals = [v for v in (get(t) for t in ts) if v is not None]
        if vals:
            out[key] = statistics.median(vals)
    return out


def regime_of(trade: dict, med: dict | None = None) -> str:
    """Coarse, cheap labels attached at trade time. Diagnostic FIRST, filter only after a
    labelled interaction survives its own validation -- creating a filter the moment losses
    cluster in a bucket is how backtests get fitted to noise."""
    if med is None:
        med = _medians(trade.get("strategy_id", ""))
    f = trade.get("feature_snapshot", {}) or {}
    bits = []
    rng, mr = f.get("pre_range"), med.get("pre_range")
    if rng is not None and mr:
        bits.append("wide_range" if rng > mr else "narrow_range")
    spr, ms = trade.get("spread"), med.get("spread")
    if spr is not None and ms:
        bits.append("wide_spread" if spr > ms else "tight_spread")
    m = f.get("minutes_since_entry", f.get("minutes_since_0630"))
    if m is not None:
        bits.append("early_break" if m <= 30 else "late_break")
    return "|".join(bits) if bits else "unlabelled"


# ==================================================================== beliefs
def belief(strategy_id: str, prior_exp: float, prior_n: int) -> dict:
    """Posterior belief about a bot, DERIVED from the full trade history every time."""
    ts = [t for t in closed_trades() if t.get("strategy_id") == strategy_id]
    n = len(ts)
    if n == 0:
        return {"strategy_id": strategy_id, "n": 0, "exp": prior_exp, "se": None, "t": None,
                "weight_live": 0.0, "source": "prior only"}
    R = [t["R"] for t in ts]
    mean = statistics.fmean(R)
    sd = statistics.stdev(R) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    k = min(prior_n, 200)
    w = n / (n + k)
    exp = w * mean + (1 - w) * prior_exp
    return {"strategy_id": strategy_id, "n": n, "live_mean": mean, "sd": sd, "se": se,
            "exp": exp, "t": (mean / se) if se and se == se and se > 0 else None,
            "weight_live": w, "wins": sum(1 for r in R if r > 0),
            "source": f"{w:.0%} live / {1-w:.0%} prior"}


def regime_table(strategy_id: str) -> dict:
    out, med = {}, _medians(strategy_id)
    for t in closed_trades():
        if t.get("strategy_id") != strategy_id:
            continue
        r = regime_of(t, med)
        out.setdefault(r, []).append(t["R"])
    return {k: {"n": len(v), "mean_R": statistics.fmean(v)} for k, v in out.items()}


def allocation(beliefs: list) -> dict:
    """Risk share per bot. Positive expectancy only, weighted by evidence-adjusted edge.

    Never martingale, never increase after a loss: allocation is a function of the WHOLE
    history, not of the last outcome. A losing streak lowers `exp` and therefore the share --
    it can never raise it.
    """
    live = {b["strategy_id"]: max(b["exp"], 0.0) * (b["weight_live"] + 0.25) for b in beliefs}
    tot = sum(live.values())
    if tot <= 0:
        return {k: 0.0 for k in live}
    return {k: round(v / tot, 4) for k, v in live.items()}


# ==================================================================== learning
def learn() -> int:
    """Ingest any closed trade the Brain has not yet seen. One lesson per trade."""
    seen = {e.get("intent_id") for e in events("trade_learned")}
    new = 0
    for t in closed_trades():
        iid = t.get("intent_id")
        if iid in seen:
            continue
        sid = t["strategy_id"]
        hist = [x["R"] for x in closed_trades()
                if x.get("strategy_id") == sid and x.get("intent_id") != iid]
        sd = statistics.stdev(hist) if len(hist) > 1 else None
        mean = statistics.fmean(hist) if hist else None
        R = t["R"]
        slip = abs(t.get("actual_slippage") or 0)

        # slippage matters in units of the trade's OWN risk, not in dollars
        sl_dist = (t.get("feature_snapshot") or {}).get("sl_dist") or t.get("sl_dist")
        slip_bad = slip > 0.1 * sl_dist if sl_dist else slip > 0.5

        if len(hist) < 10:
            lesson = "INSUFFICIENT_DATA"
        elif slip_bad:
            lesson = "EXECUTION_PROBLEM"
        elif sd and R < mean - 3 * sd:
            lesson = "REGIME_MISMATCH"
        else:
            lesson = "EXPECTED_WIN" if R > 0 else "EXPECTED_LOSS"

        emit("trade_learned", intent_id=iid, strategy_id=sid, R=R,
             regime=regime_of(t), lesson=lesson, slippage=slip,
             outcome=t.get("outcome"), spread=t.get("spread"))
        new += 1
    if new:
        emit("beliefs_updated", n_new_trades=new)
    return new


def weekly_review(bots: list) -> dict:
    """The compounding step. Rank, retire, promote, reallocate -- on evidence, not on mood."""
    bel = [belief(b["strategy_id"], b["prior_exp"], b["prior_n"]) for b in bots]
    alloc = allocation(bel)
    actions = []
    for b, be in zip(bots, bel):
        sid, n, t = be["strategy_id"], be["n"], be.get("t")
        if n >= RETIRE_MIN_TRADES and t is not None and t <= RETIRE_T:
            actions.append({"strategy_id": sid, "action": "RETIRE",
                            "why": f"live t={t:+.2f} over n={n} -- edge not present"})
        elif n >= PROMOTE_MIN_TRADES and t is not None and t >= PROMOTE_T:
            actions.append({"strategy_id": sid, "action": "PROMOTE_DEMO_PROVEN",
                            "why": f"live t={t:+.2f} over n={n}"})
        elif n >= RETIRE_MIN_TRADES and t is not None and t < 0:
            # NOT a retirement. Diagnose before deleting -- the charter says repair first.
            rt = regime_table(sid)
            worst = min(rt.items(), key=lambda kv: kv[1]["mean_R"]) if rt else None
            actions.append({"strategy_id": sid, "action": "DIAGNOSE",
                            "why": f"live t={t:+.2f}; worst regime "
                                   f"{worst[0] if worst else 'n/a'} "
                                   f"({worst[1]['mean_R']:+.3f}R over n={worst[1]['n']})"
                                   if worst else f"live t={t:+.2f}"})
        else:
            actions.append({"strategy_id": sid, "action": "CONTINUE",
                            "why": f"n={n}, insufficient evidence to act"})
    n_active = sum(1 for a in actions if a["action"] != "RETIRE")
    if n_active < 5:
        actions.append({"strategy_id": None, "action": "GENERATE_CANDIDATE",
                        "why": f"only {n_active} live bots; desk target is 5"})
    emit("weekly_review", beliefs=bel, allocation=alloc, actions=actions)
    return {"beliefs": bel, "allocation": alloc, "actions": actions}


# ==================================================================== recall
def recall(strategy_id: str, prior_exp: float, prior_n: int) -> dict:
    """WHAT THE CONTROLLER ASKS BEFORE IT SIZES A TRADE.

    This is the function that makes the Brain a brain rather than an archive: its return value
    changes the size of the next order.
    """
    be = belief(strategy_id, prior_exp, prior_n)
    lessons = [e for e in events("trade_learned") if e.get("strategy_id") == strategy_id]
    recent = lessons[-10:]
    exec_problems = sum(1 for e in recent if e["lesson"] == "EXECUTION_PROBLEM")
    mismatches = sum(1 for e in recent if e["lesson"] == "REGIME_MISMATCH")
    # risk multiplier: evidence-driven, bounded, and it can only REDUCE below 1.0 without
    # sustained positive evidence. It never responds to a single outcome.
    mult = 1.0
    if be["n"] >= 10 and be.get("t") is not None:
        if be["t"] <= -1.0:
            mult = 0.5
        elif be["t"] >= 1.5 and be["n"] >= PROMOTE_MIN_TRADES:
            mult = 1.5
    if exec_problems >= 3:
        mult = min(mult, 0.5)
    return {"belief": be, "risk_multiplier": round(mult, 3),
            "recent_execution_problems": exec_problems, "recent_regime_mismatch": mismatches,
            "regimes": regime_table(strategy_id),
            "n_events": len(events()), "why": f"{be['source']}, mult {mult}"}


# ==================================================================== realised risk
RISK_OVERRUN_R = -1.5             # planned risk was not what actually happened
RISK_OBSERVATION_R = -2.0         # bad enough to stop risking money until understood


def risk_audit(strategy_id: str | None = None) -> list:
    """planned vs REALISED loss. BOT_D planned $24 and lost $148; nothing in the posterior
    would ever have flagged that, because -6R is just a very bad trade to an expectancy
    calculation. Risk realisation is a separate question from edge and needs its own alarm."""
    out = []
    for t in closed_trades():
        if strategy_id and t.get("strategy_id") != strategy_id:
            continue
        R = t.get("R")
        if R is None or R >= RISK_OVERRUN_R:
            continue
        planned = (t.get("risk_pct") or 0) * (t.get("account_equity") or 0)
        out.append({
            "intent_id": t.get("intent_id"), "strategy_id": t.get("strategy_id"),
            "planned_risk_money": planned, "realized_loss_money": t.get("net"),
            "realized_R": R,
            "overrun_x": abs(R),
            "flag": "OBSERVATION" if R <= RISK_OBSERVATION_R else "RISK_OVERRUN",
            "stop": t.get("stop"), "exit": t.get("exit"),
            "slip_past_stop": (abs((t.get("exit") or 0) - (t.get("stop") or 0))
                               if t.get("exit") and t.get("stop") else None),
            "holding_minutes": t.get("holding_minutes"),
        })
    return out


def forced_states(bots: list) -> dict:
    """A bot with a realised loss worse than -2R goes to OBSERVATION until the cause is
    understood. This is a RISK response, not a verdict on the edge -- the entry hypothesis
    stays alive and keeps being recorded."""
    st = {}
    for b in bots:
        sid = b["strategy_id"]
        bad = [a for a in risk_audit(sid) if a["flag"] == "OBSERVATION"]
        if bad:
            st[sid] = {"state": "OBSERVATION", "n_overruns": len(bad),
                       "worst_R": min(a["realized_R"] for a in bad),
                       "why": f"realised {min(a['realized_R'] for a in bad):+.2f}R vs planned "
                              f"-1R -- risk geometry unproven, entry hypothesis untouched"}
    return st


# ==================================================================== scoreboard
def execution_quality(strategy_id: str) -> dict:
    """Can this bot actually be traded? Separate from whether it is profitable."""
    ts = [t for t in closed_trades() if t.get("strategy_id") == strategy_id]
    if not ts:
        return {"n": 0, "slip_R": None, "fill_rate": None}
    def slip_R(t):
        sl = (t.get("feature_snapshot") or {}).get("sl_dist") or abs(
            (t.get("entry") or 0) - (t.get("stop") or 0)) or None
        s = abs(t.get("actual_slippage") or 0)
        return s / sl if sl else None
    v = [x for x in (slip_R(t) for t in ts) if x is not None]
    return {"n": len(ts), "slip_R": statistics.fmean(v) if v else None,
            "avg_mfe_R": statistics.fmean([t["mfe_R"] for t in ts if t.get("mfe_R") is not None])
            if any(t.get("mfe_R") is not None for t in ts) else None,
            "avg_mae_R": statistics.fmean([t["mae_R"] for t in ts if t.get("mae_R") is not None])
            if any(t.get("mae_R") is not None for t in ts) else None,
            "swap_paid": sum(t.get("swap") or 0 for t in ts)}


def pass_contribution(be: dict, risk: float = 0.0010) -> float:
    """Crude expected contribution to the +10% target per 20 trades, in account %.
    Deliberately crude -- a precise number here would be false precision on n<40."""
    return be["exp"] * risk * 20 * 100


def scoreboard(bots: list) -> list:
    rows = []
    for b in bots:
        be = belief(b["strategy_id"], b["prior_exp"], b["prior_n"])
        eq = execution_quality(b["strategy_id"])
        # confidence: how much of this belief is live evidence rather than assumption
        rows.append({**be, "stage": b.get("stage"), "symbol": b.get("symbol"),
                     "confidence": be["weight_live"], "exec": eq,
                     "contrib_pct": pass_contribution(be)})
    rows.sort(key=lambda r: (-(r["confidence"] > 0), -r["exp"]))
    return rows


def cmd_scoreboard(bots):
    rows = scoreboard(bots)
    alloc = allocation(rows)
    print("=" * 94)
    print(f" BOT SCOREBOARD — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    print("=" * 94)
    print(f" {'bot':<32}{'n':>4}{'expR':>8}{'t':>7}{'conf':>7}{'slipR':>8}"
          f"{'contrib':>9}{'alloc':>8}")
    for r in rows:
        t = r.get("t")
        sl = r["exec"].get("slip_R")
        print(f" {r['strategy_id']:<32}{r['n']:>4}{r['exp']:>+8.3f}"
              f"{(f'{t:+.2f}' if t is not None else '--'):>7}{r['confidence']:>7.0%}"
              f"{(f'{sl:.3f}' if sl is not None else '--'):>8}"
              f"{r['contrib_pct']:>+8.2f}%{alloc.get(r['strategy_id'], 0):>8.0%}")
    live = sum(1 for r in rows if r["n"] > 0)
    tot = sum(r["contrib_pct"] for r in rows)
    print(f"\n {live}/{len(rows)} bots have live evidence.  "
          f"combined expected contribution {tot:+.2f}% per 20 trades each")
    if live == 0:
        print(" NO LIVE EVIDENCE YET -- every number above is prior, i.e. assumption.")
    emit("scoreboard", rows=[{k: v for k, v in r.items() if k != "exec"} for r in rows],
         allocation=alloc)


# ==================================================================== cli
def _bots():
    """Read bot identity from the controller so the two can never disagree."""
    sys.path.insert(0, str(ROOT))
    try:
        from challenge_controller import BOTS
        return [{"strategy_id": b.strategy_id, "prior_exp": b.prior_expectancy_R,
                 "prior_n": b.prior_n, "stage": b.stage, "symbol": b.symbol} for b in BOTS]
    except Exception as e:
        print(f"  (could not import controller bots: {e})")
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recall", action="store_true")
    ap.add_argument("--learn", action="store_true")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--scoreboard", action="store_true")
    ap.add_argument("--void-existing", metavar="REASON",
                    help="mark every currently-closed trade's EVIDENCE void (ledger untouched)")
    a = ap.parse_args()
    bots = _bots()

    if a.void_existing:
        ids = [t["intent_id"] for t in closed_trades(include_voided=True)]
        if not ids:
            print("nothing to void"); return
        emit("evidence_voided", intent_ids=ids, reason=a.void_existing, n=len(ids))
        print(f"VOIDED the evidence of {len(ids)} closed trade(s).")
        print(f"  reason: {a.void_existing}")
        print(f"  the ledger is UNCHANGED -- every row is still there and still auditable.")
        print(f"  posteriors now revert to priors until new trades arrive.")
        return

    if a.scoreboard:
        cmd_scoreboard(bots); return

    if a.learn:
        n = learn()
        print(f"learned from {n} new closed trade(s); {len(events())} events total")
        return

    if a.weekly:
        r = weekly_review(bots)
        print("=" * 80)
        print(" WEEKLY REVIEW")
        print("=" * 80)
        print(f"  {'bot':<30}{'n':>5}{'expR':>9}{'t':>8}{'alloc':>9}")
        for b in r["beliefs"]:
            t = b.get("t")
            print(f"  {b['strategy_id']:<30}{b['n']:>5}{b['exp']:>+9.3f}"
                  f"{(f'{t:+.2f}' if t is not None else '--'):>8}"
                  f"{r['allocation'].get(b['strategy_id'],0):>9.1%}")
        print("\n  ACTIONS")
        for x in r["actions"]:
            print(f"    {str(x['strategy_id'] or 'DESK'):<30}{x['action']:<24}{x['why']}")
        return

    # default: recall
    print("=" * 80)
    print(f" TRADING BRAIN — {len(events())} events, {len(closed_trades())} closed trades")
    print("=" * 80)
    if not bots:
        print("  no bots registered")
        return
    for b in bots:
        r = recall(b["strategy_id"], b["prior_exp"], b["prior_n"])
        be = r["belief"]
        print(f"\n  {b['strategy_id']}  [{b['stage']}]")
        print(f"    belief      exp {be['exp']:+.3f}R  n={be['n']}  ({be['source']})")
        print(f"    risk mult   x{r['risk_multiplier']}  -- {r['why']}")
        if r["regimes"]:
            print(f"    regimes:")
            for k, v in sorted(r["regimes"].items(), key=lambda kv: kv[1]["mean_R"]):
                print(f"      {k:<40}n={v['n']:<4} {v['mean_R']:+.3f}R")
        else:
            print(f"    regimes     none yet -- labels attach as trades close")
    print(f"\n  events are APPEND-ONLY: {EVENTS}")
    print(f"  beliefs are DERIVED on every read, so they can never drift from the evidence.")


if __name__ == "__main__":
    main()
