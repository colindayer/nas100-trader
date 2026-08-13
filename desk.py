"""THE DESK — the market is asked first, and the CIO allocates. Bots are specialists.

    py desk.py                    what the market is offering right now, and who gets it

INVERSION
  The controller used to ask each bot "do you want to trade?" and filter afterwards. That
  makes every bot its own allocator and guarantees correlated exposure: five specialists in
  one mechanism all answer yes to the same market. Now the market is classified FIRST, then
  the CIO hands the opportunity to the specialists declared for it.

WHAT IS STRUCTURAL VS WHAT NEEDS DATA
  Structural, correct at n=0 and implemented here:
    - opportunity classification (a reading of state, not a prediction)
    - specialist declarations (a fade bot avoids strong trend BY CONSTRUCTION)
    - correlation caps (five bots sharing a playbook are one bet)
    - coverage gaps (an opportunity class with no specialist is visible immediately)
  Needs data, deliberately NOT implemented:
    - state-conditional expectancy ("who is best in STATE_07")
    - shadow promotion
  Those return INSUFFICIENT_EVIDENCE until the samples exist. Weighting allocation by an
  expectancy measured on five trades would be noise wearing a CIO's hat.
"""
from __future__ import annotations

import sys

# Windows consoles default to cp1252 and cannot encode arrows. Pin stdout so a report never
# dies on an encoding error after a full day of trading.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ==================================================================== opportunity classes
STRONG_TREND = "STRONG_TREND"
WEAK_TREND = "WEAK_TREND"
TRANSITION = "TRANSITION"
RANGE = "RANGE"
COMPRESSION = "COMPRESSION"
EXPANSION = "EXPANSION"
EXTENDED = "EXTENDED"
AT_HTF_LEVEL = "AT_HTF_LEVEL"
RISK_ON = "RISK_ON"
RISK_OFF = "RISK_OFF"
USD_STRONG = "USD_STRONG"
USD_WEAK = "USD_WEAK"
UNKNOWN = "UNKNOWN"

# A REGIME is what the market IS -- exactly one holds at a time, and a specialist designed
# for the wrong one is structurally wrong. A MODIFIER is a qualifier that colours it.
# Conflating them froze the desk: EXTENDED and COMPRESSION fire on most days, so putting
# them in `avoids` made ordinary conditions into universal vetoes.
REGIMES = {STRONG_TREND, WEAK_TREND, RANGE, TRANSITION, UNKNOWN}
MODIFIERS = {COMPRESSION, EXPANSION, EXTENDED, AT_HTF_LEVEL,
             RISK_ON, RISK_OFF, USD_STRONG, USD_WEAK}

MIN_EXPERIMENTAL_RISK = 0.0005      # the desk always has a way to learn something


def classify_opportunity(state: dict) -> dict:
    """READ the market. This predicts nothing -- every branch is a description of state
    that already exists, so it cannot be fitted and needs no sample to be valid."""
    o, why = [], {}
    d1, h4 = state.get("d1_regime"), state.get("h4_regime")
    ts = state.get("d1_trend_strength_atr")

    if d1 in ("up", "down"):
        # both timeframes agreeing is a materially different market from D1 alone
        if h4 == d1:
            o.append(STRONG_TREND); why[STRONG_TREND] = f"d1 and h4 both {d1}"
        else:
            o.append(WEAK_TREND); why[WEAK_TREND] = f"d1 {d1}, h4 {h4}"
    elif d1 == "range":
        o.append(RANGE); why[RANGE] = "price near a flat d1 mean"
    elif d1 == "transition":
        o.append(TRANSITION); why[TRANSITION] = f"d1 unconfirmed, h4 {h4}"
    else:
        o.append(UNKNOWN); why[UNKNOWN] = f"d1 regime {d1}"

    ve = state.get("vol_expansion")
    if ve is not None:
        if ve >= 1.2:
            o.append(EXPANSION); why[EXPANSION] = f"5d range {ve:.2f}x the 20d"
        elif ve <= 0.8:
            o.append(COMPRESSION); why[COMPRESSION] = f"5d range {ve:.2f}x the 20d"

    if ts is not None and abs(ts) >= 2.0:
        o.append(EXTENDED); why[EXTENDED] = f"{ts:+.2f} ATR from the d1 mean"

    side_room = [state.get("room_above_atr"), state.get("room_below_atr")]
    near = [r for r in side_room if r is not None and r < 0.5]
    if near:
        o.append(AT_HTF_LEVEL); why[AT_HTF_LEVEL] = f"{min(near):.2f} ATR to a level"

    for k in ("macro_risk", "macro_usd"):
        v = state.get(k)
        if v in (RISK_ON, RISK_OFF, USD_STRONG, USD_WEAK):
            o.append(v); why[v] = k

    return {"opportunities": o, "why": why}


# ==================================================================== playbooks
# Shared mechanics. Improving a playbook improves every specialist inheriting it, so a fix
# is written once rather than drifting across five near-identical bots.
PLAYBOOKS = {
    "BREAKOUT": {
        "wants": {EXPANSION, STRONG_TREND, WEAK_TREND},
        "avoids": {COMPRESSION, EXTENDED, RANGE},
        "rationale": "a break needs somewhere to go: range to escape, volatility to carry it",
    },
    "REVERSION": {
        "wants": {RANGE, COMPRESSION},
        "avoids": {STRONG_TREND, EXPANSION, TRANSITION},
        "rationale": "fading requires a mean that holds; in a trend the mean moves to price",
    },
    "SWEEP": {
        "wants": {TRANSITION, AT_HTF_LEVEL, EXTENDED, RANGE},
        "avoids": {STRONG_TREND},
        "rationale": "trades a level that FAILS -- needs an unconfirmed market where a push "
                     "beyond a reference gets rejected, which is exactly what breakout and "
                     "continuation specialists cannot use",
    },
    "CONTINUATION": {
        "wants": {STRONG_TREND, EXPANSION},
        "avoids": {RANGE, COMPRESSION, TRANSITION},
        "rationale": "holds an existing move; needs the move to be real and confirmed",
    },
}


def eligibility(bot, opportunities: list) -> tuple[bool, str]:
    """HARD block only. A specialist is refused when the REGIME is one it cannot trade --
    a fade bot in a strong trend is structurally wrong, not merely unlucky. Modifiers never
    block; they price the opportunity down in utility()."""
    pb = PLAYBOOKS.get(getattr(bot, "playbook", ""), {})
    avoid = (set(getattr(bot, "avoids", set())) | set(pb.get("avoids", set()))) & REGIMES
    opp = set(opportunities)
    blocked = opp & avoid
    if blocked:
        return False, f"regime {', '.join(sorted(blocked))} is structurally wrong for this bot"
    return True, "eligible"


def utility(bot, opportunities: list, belief: dict | None = None) -> dict:
    """Expected utility, always a number -- never a refusal. The CIO ranks; it does not wait.

    Modifiers apply penalties rather than vetoes, so an imperfect match still competes and
    the desk keeps learning. Only the Risk Manager stops a trade outright.
    """
    pb = PLAYBOOKS.get(getattr(bot, "playbook", ""), {})
    wants = set(getattr(bot, "primary", set())) | set(pb.get("wants", set()))
    secondary = set(getattr(bot, "secondary", set()))
    dislikes = (set(getattr(bot, "avoids", set())) | set(pb.get("avoids", set()))) & MODIFIERS
    opp = set(opportunities)

    regime = next((o for o in opp if o in REGIMES), UNKNOWN)
    if regime in wants:
        fit, why = 1.0, f"primary regime {regime}"
    elif regime in secondary:
        fit, why = 0.6, f"secondary regime {regime}"
    elif regime == UNKNOWN:
        fit, why = 0.25, "regime unknown"
    else:
        fit, why = 0.35, f"neutral in {regime}"

    penalties = sorted(opp & dislikes)
    score = fit * (0.65 ** len(penalties))
    liked = sorted((opp & MODIFIERS) & wants)
    score *= 1.15 ** len(liked)

    # posterior expectancy nudges the ranking but cannot dominate it at small n --
    # a 5-trade sample must not out-vote a structural mismatch in either direction.
    exp_factor = 1.0
    if belief and belief.get("n", 0) > 0:
        exp_factor = max(0.5, min(1.5, 1.0 + (belief.get("exp") or 0.0)))
        why += f", posterior {belief['exp']:+.2f}R on n={belief['n']}"
    score *= exp_factor

    return {"score": round(score, 4), "fit": fit, "regime": regime,
            "penalties": penalties, "boosts": liked, "why": why}


# ==================================================================== CIO allocation
def correlation_group(bot) -> str:
    """Bots sharing a playbook are ONE BET however many symbols they hold. On 2026-08-12
    three breakout bots lost within 31 minutes across two instruments; counting that as
    three independent failures is how a book gets mistaken for a portfolio."""
    return getattr(bot, "playbook", "UNGROUPED")


def allocate(bots, opportunities_by_symbol: dict, risk_of, challenge_state,
             group_cap=0.0015, total_cap=0.0075, beliefs=None) -> dict:
    """Bots propose, the CIO allocates. Ranks by expected utility and ALWAYS funds the best
    eligible specialist at minimum experimental risk.

    The desk is paid to decide under uncertainty. Freezing because no specialist is a perfect
    match returns zero information and zero P&L; a 0.05% probe returns one observation. Only
    HARD safety reasons stop a trade: wrong regime for the specialist, correlated-group cap,
    total risk cap, or a challenge-drawdown veto.
    """
    decisions, group_used, total = {}, {}, 0.0
    beliefs = beliefs or {}
    scored = []
    for bot in bots:
        opp = opportunities_by_symbol.get(bot.symbol, {}).get("opportunities", [])
        ok, why = eligibility(bot, opp)
        u = utility(bot, opp, beliefs.get(bot.strategy_id))
        if not ok:
            decisions[bot.strategy_id] = {"allow": False, "risk": 0.0, "reason": why,
                                          "utility": 0.0}
            continue
        scored.append((u["score"], bot, u))
    scored.sort(key=lambda x: -x[0])

    for rank, (score, bot, u) in enumerate(scored):
        want = risk_of(bot)
        # A SHADOW risks nothing, so it must not consume the correlated-group or total cap --
        # otherwise an unproven candidate crowds a live specialist out of the budget while
        # having no capital at stake. It is still ranked and still records everything.
        if getattr(bot, "shadow", False):
            decisions[bot.strategy_id] = {
                "allow": True, "risk": want, "utility": score, "shadow": True,
                "reason": f"SHADOW -- {u['why']}; records only, no capital, no cap consumed",
                "group": correlation_group(bot)}
            continue
        # nothing is a perfect match today -> still fund the best one, minimally
        if rank == 0 and u["fit"] < 0.6:
            want = min(want, MIN_EXPERIMENTAL_RISK)
            u["why"] += " -- imperfect match, minimum probe to keep learning"
        elif u["fit"] < 0.6:
            decisions[bot.strategy_id] = {
                "allow": False, "risk": 0.0, "utility": score,
                "reason": f"outranked ({u['why']}); desk probes only its best candidate "
                          f"when no specialist fits"}
            continue
        g = correlation_group(bot)
        used = group_used.get(g, 0.0)
        if used + want > group_cap:
            decisions[bot.strategy_id] = {
                "allow": False, "risk": 0.0,
                "reason": f"{g} group at {used:.3%} of {group_cap:.2%} cap "
                          f"-- correlated exposure, not diversification"}
            continue
        if total + want > total_cap:
            decisions[bot.strategy_id] = {
                "allow": False, "risk": 0.0,
                "reason": f"desk at {total:.3%} of {total_cap:.2%} total cap"}
            continue

        veto = challenge_state.veto(want) if challenge_state else None
        if veto:
            decisions[bot.strategy_id] = {"allow": False, "risk": 0.0, "utility": score,
                                          "reason": f"RISK MANAGER veto: {veto}"}
            continue

        group_used[g] = used + want
        total += want
        decisions[bot.strategy_id] = {"allow": True, "risk": want, "utility": score,
                                      "reason": u["why"], "group": g,
                                      "penalties": u["penalties"]}
    return {"decisions": decisions, "group_used": group_used, "total_risk": total,
            "ranking": [(b.strategy_id, s) for s, b, _ in scored]}


# ==================================================================== desk knowledge
def coverage(bots, opportunities: list) -> dict:
    """Which opportunity classes has this desk no specialist for? A gap is visible on day
    one -- it needs no evidence, only an inventory."""
    covered, gaps = {}, []
    # Only REGIMES can be gaps. A modifier is not a market to specialise in, and reporting
    # "no specialist for RISK_ON" is noise that makes a healthy desk look broken.
    for o in [x for x in opportunities if x in REGIMES]:
        who = [b.strategy_id for b in bots
               if eligibility(b, [o])[0] and utility(b, [o])["fit"] >= 0.6]
        covered[o] = who
        if not who:
            gaps.append(o)
    return {"covered": covered, "gaps": gaps,
            "note": "gaps are work orders for the Bot Factory, not reasons to stop trading"}


MIN_STATES_FOR_CONDITIONAL = 30


def state_conditional_edge(closed_trades: list, opportunity: str) -> dict:
    """"Who is best in this market?" -- refuses to answer until it honestly can.

    Returning a ranking from five trades would be noise with a CIO's authority attached,
    and the desk would then allocate on it.
    """
    import statistics
    rows = {}
    for t in closed_trades:
        st = t.get("market_state") or {}
        opps = classify_opportunity(st)["opportunities"]
        if opportunity not in opps or t.get("R") is None:
            continue
        rows.setdefault(t["strategy_id"], []).append(t["R"])
    n = sum(len(v) for v in rows.values())
    if n < MIN_STATES_FOR_CONDITIONAL:
        return {"status": "INSUFFICIENT_EVIDENCE", "n": n,
                "need": MIN_STATES_FOR_CONDITIONAL, "opportunity": opportunity,
                "by_bot": {k: len(v) for k, v in rows.items()}}
    return {"status": "OK", "n": n, "opportunity": opportunity,
            "by_bot": {k: {"n": len(v), "exp_R": statistics.fmean(v)}
                       for k, v in rows.items()}}


def main():
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import MetaTrader5 as mt5, pandas as pd
    import market_state as MS, macro_context as MC
    from challenge_controller import BOTS, risk_for

    if not mt5.initialize():
        raise SystemExit(f"initialize failed: {mt5.last_error()}")
    now = pd.Timestamp.now(tz="Europe/London")
    by_symbol, all_opps = {}, set()
    for sym in sorted({b.symbol for b in BOTS}):
        mt5.symbol_select(sym, True)
        t = mt5.symbol_info_tick(sym)
        if t is None:
            continue
        st = MS.compute(mt5, sym, now, t.ask, t.ask - t.bid)
        st.update(MC.compute(mt5, sym, now))
        by_symbol[sym] = classify_opportunity(st)
        all_opps |= set(by_symbol[sym]["opportunities"])

    print("=" * 88)
    print(f" WHAT THE MARKET IS OFFERING — {now:%Y-%m-%d %H:%M} London")
    print("=" * 88)
    for sym, o in by_symbol.items():
        print(f"\n  {sym}")
        for k in o["opportunities"]:
            print(f"    {k:<16}{o['why'].get(k,'')}")

    cov = coverage(BOTS, sorted(all_opps))
    print("\n" + "=" * 88)
    print(" SPECIALIST COVERAGE")
    print("=" * 88)
    for o, who in cov["covered"].items():
        print(f"  {o:<16}{', '.join(who) if who else '** NO SPECIALIST **'}")
    if cov["gaps"]:
        print(f"\n  COVERAGE GAPS: {', '.join(cov['gaps'])}")
        print("  The desk can observe these markets and cannot act in them.")

    print("\n" + "=" * 88)
    print(" CIO ALLOCATION")
    print("=" * 88)
    try:
        from trading_brain import belief
        beliefs = {b.strategy_id: belief(b.strategy_id, b.prior_expectancy_R, b.prior_n)
                   for b in BOTS}
    except Exception:
        beliefs = {}
    a = allocate(BOTS, by_symbol, lambda b: b.risk_override or 0.0010, None, beliefs=beliefs)
    print(f"  {'bot':<32}{'utility':>8}  decision")
    for sid, d in sorted(a["decisions"].items(), key=lambda kv: -kv[1].get("utility", 0)):
        mark = f"FUND {d['risk']:.3%}" if d["allow"] else "     --    "
        print(f"  {sid:<32}{d.get('utility', 0):>8.3f}  {mark}  {d['reason']}")
    print(f"\n  groups: {a['group_used']}   total risk {a['total_risk']:.3%}")
    if a["total_risk"] == 0:
        print("  DESK IDLE -- every candidate hard-blocked or vetoed. Check the reasons above.")
    mt5.shutdown()


if __name__ == "__main__":
    main()
