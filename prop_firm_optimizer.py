"""
prop_firm_optimizer.py — Monte-Carlo prop-challenge optimizer for the VALIDATED
3-pillar system (Nasdaq sweep+ORB, Gold FVG, BTC sweep — see FINDINGS.md).

Answers, per firm preset and per aggression level (== RISK_SCALE in config.ini):
  • P(pass each phase) and P(reach funded)
  • median market days to funded (speed — "fast convenient numbers")
  • expected COST to get funded (fees / P(pass))
  • EV per challenge and EV per 30 market days (speed-adjusted EV)
  • expected funded income over a 24-month horizon, WITH the validated
    conformal dd-throttle applied on the funded account

Presets: FundedNext Stellar 2-Step / 1-Step / Stellar Lite, FTMO (comparison).
Rules sourced 2026-07: help.fundednext.com (targets, daily loss, max loss,
min trading days). FEES are approximate list prices — edit before trusting EV.

P&L MODEL (honest by construction — read this):
  Daily returns are ZERO-INFLATED STUDENT-T (df=4):
    - only ~P_TRADE of market days have any P&L (the system trades sparsely),
    - active days draw a fat-tailed t, calibrated so the 1x annual mean/vol
      match the measured 3-pillar backtest (CAGR +12.2%, vol ~8.8%, Sharpe 1.38).
  Symmetric fat tails are CONSERVATIVE for this system (real edge is +skewed:
  3:1 RR, ~39% WR — big days are more often UP), so breach probabilities here
  should be worst-case-ish, not optimistic.
  The daily-loss rule is checked against 80% of the stated limit
  (INTRADAY_BUFFER) because firms measure INTRADAY equity, not close-to-close.

  Aggression multiplies BOTH mean and vol (Sharpe-invariant) — exactly what
  RISK_SCALE does to position sizes.

EDGE SCENARIOS: the whole exercise is garbage-in/garbage-out on the edge being
real live. Three scenarios are simulated:
    backtest : mean = measured 3-pillar CAGR (+12.2%/yr, Sharpe 1.38)
    haircut  : mean × 0.66  (≈ +8%/yr, Sharpe ~0.9)  ← REALISTIC, headline
    weak     : mean × 0.33  (≈ +4%/yr, Sharpe ~0.45) ← stress
"""
import numpy as np

rng = np.random.default_rng(7)

# ── 1x edge calibration (RISK_SCALE = 1.0), from FINDINGS.md 3-pillar capstone ─
CAGR_1X   = 0.122      # measured combined CAGR net of costs
VOL_1X    = 0.088      # implied by Sharpe 1.38
P_TRADE   = 0.40       # fraction of market days with any P&L (sparse book)
T_DF      = 4          # Student-t tail df (heavy)
TD        = 252
INTRADAY_BUFFER = 0.80 # daily-loss rule checked at 80% of stated limit
MAX_DAYS  = 252        # sim horizon per phase (all firms here have no time limit)
N_PATHS   = 8000
FUND_MONTHS = 24
DAYS_PER_M  = 21
THROTTLE_FLOOR = 0.30  # conformal dd-throttle floor (see conformal_overlay.py)

EDGE_SCENARIOS = {"backtest": 1.00, "haircut": 0.66, "weak": 0.33}
MULTS = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]

# ── Firm presets ───────────────────────────────────────────────────────────────
# phases: list of (profit_target, min_trading_days). daily/max losses are
# fractions of INITIAL balance (FundedNext Stellar & FTMO are static, not trailing).
# fee = approximate $ for a $100k account (EDIT to current list price).
PRESETS = {
    "FN Stellar 2-Step": dict(phases=[(0.08, 5), (0.05, 5)], daily=0.05,
                              maxdd=0.10, fee=549.0, split=0.80, refund=True),
    "FN Stellar 1-Step": dict(phases=[(0.10, 2)], daily=0.03,
                              maxdd=0.06, fee=569.0, split=0.80, refund=False),
    "FN Stellar Lite":   dict(phases=[(0.08, 5), (0.04, 5)], daily=0.04,
                              maxdd=0.08, fee=299.0, split=0.80, refund=True),
    "FTMO (compare)":    dict(phases=[(0.10, 4), (0.05, 4)], daily=0.05,
                              maxdd=0.10, fee=590.0, split=0.80, refund=True),
}
ACCOUNT = 100_000.0


def daily_returns(mult, edge, n, days):
    """Zero-inflated Student-t daily returns at given aggression multiplier."""
    mu_active  = (CAGR_1X * edge) / (TD * P_TRADE)            # mean on active days
    # t(df) variance = df/(df-2)  → scale so annualized vol matches VOL_1X
    sig_active = VOL_1X / np.sqrt(TD * P_TRADE * T_DF / (T_DF - 2))
    active = rng.random((n, days)) < P_TRADE
    t = rng.standard_t(T_DF, size=(n, days))
    return active * (mu_active + sig_active * t) * mult, active


def sim_phase(target, min_days, daily, maxdd, mult, edge, n):
    """Returns (passed, days_to_pass, breached). Additive equity (small-r approx)."""
    r, active = daily_returns(mult, edge, n, MAX_DAYS)
    eq = 1.0 + r.cumsum(axis=1)
    day_breach = (r <= -(daily * INTRADAY_BUFFER)).cumsum(axis=1) > 0
    dd_breach  = (eq <= 1.0 - maxdd).cumsum(axis=1) > 0
    dead = day_breach | dd_breach
    enough_days = active.cumsum(axis=1) >= min_days
    hit = (eq >= 1.0 + target) & enough_days & ~dead
    passed = hit.any(axis=1)
    days = np.where(passed, hit.argmax(axis=1) + 1, MAX_DAYS)
    breached = dead.any(axis=1) & ~passed
    return passed, days, breached


def funded_income(daily, maxdd, split, mult, edge, n):
    """Cumulative payout (fraction of account) over FUND_MONTHS, with the
    validated conformal dd-throttle scaling size by drawdown headroom."""
    total = np.zeros(n)
    alive = np.ones(n, dtype=bool)
    target_dd = maxdd * 0.8                      # throttle aims inside the cap
    for _ in range(FUND_MONTHS):
        r, _ = daily_returns(mult, edge, n, DAYS_PER_M)
        eq = np.ones(n)
        peak = np.ones(n)
        dead_m = np.zeros(n, dtype=bool)
        for d in range(DAYS_PER_M):
            head = (target_dd + (eq - peak) / peak) / target_dd
            sc = np.clip(head, THROTTLE_FLOOR, 1.0)
            step = sc * r[:, d]
            dead_m |= step <= -(daily * INTRADAY_BUFFER)
            eq = eq + step
            peak = np.maximum(peak, eq)
            dead_m |= eq <= 1.0 - maxdd
        pay = np.where(~dead_m & (eq > 1.0), (eq - 1.0) * split, 0.0)
        total += np.where(alive, pay, 0.0)
        alive &= ~dead_m
    return total


def run_preset(name, cfg, edge):
    print(f"\n  {name}:  targets {'/'.join(f'{t:.0%}' for t, _ in cfg['phases'])}"
          f", daily {cfg['daily']:.0%}, max {cfg['maxdd']:.0%}, fee ${cfg['fee']:.0f}"
          f"{' (refunded)' if cfg['refund'] else ''}")
    print(f"  {'Risk':>5} | {'P(pass)':>7} | {'med days':>8} | {'P(breach)':>9} | "
          f"{'$→funded':>9} | {'EV/chal':>8} | {'EV/30d':>7} | {'funded$24m':>10}")
    print("  " + "-" * 82)
    best = None
    for m in MULTS:
        p_all = np.ones(N_PATHS, dtype=bool)
        days_all = np.zeros(N_PATHS)
        breach_any = np.zeros(N_PATHS, dtype=bool)
        for target, mind in cfg["phases"]:
            p, d, b = sim_phase(target, mind, cfg["daily"], cfg["maxdd"], m, edge, N_PATHS)
            days_all += np.where(p_all, d, 0)
            breach_any |= p_all & b
            p_all &= p
        p_pass = p_all.mean()
        med_days = np.median(days_all[p_all]) if p_pass > 0 else float("nan")
        inc = funded_income(cfg["daily"], cfg["maxdd"], cfg["split"], m, edge, N_PATHS)
        inc_usd = inc.mean() * ACCOUNT
        ev = -cfg["fee"] + p_pass * ((cfg["fee"] if cfg["refund"] else 0.0) + inc_usd)
        cost_to_fund = cfg["fee"] / p_pass if p_pass > 0 else float("inf")
        # speed-adjusted EV: expected days burned per attempt ≈ pass-days or breach point
        ev_per_30d = ev / max(med_days, 1) * 30 if p_pass > 0 else -cfg["fee"]
        print(f"  {m:>4.2f}x | {p_pass:>7.1%} | {med_days:>8.0f} | "
              f"{breach_any.mean():>9.1%} | ${cost_to_fund:>8,.0f} | "
              f"${ev:>7,.0f} | ${ev_per_30d:>6,.0f} | ${inc_usd:>9,.0f}")
        score = ev_per_30d
        if best is None or score > best[0]:
            best = (score, m, p_pass, med_days, ev)
    _, m, p, d, ev = best
    print(f"  >>> speed-EV optimum: {m}x  (P(pass) {p:.0%}, ~{d:.0f} market days, "
          f"EV ${ev:,.0f}/challenge)")
    return name, best


print("=" * 88)
print(f"PROP-FIRM CHALLENGE OPTIMIZER — 3-pillar system, $"
      f"{ACCOUNT:,.0f} accounts, {N_PATHS} MC paths")
print(f"1x edge = CAGR {CAGR_1X:+.1%}, vol {VOL_1X:.1%}, fat tails t({T_DF}), "
      f"trade days {P_TRADE:.0%}, intraday buffer {INTRADAY_BUFFER:.0%}")
print("Aggression 'Risk' == RISK_SCALE in config.ini (dd-throttle ON when funded)")
print("=" * 88)

for scen, edge in EDGE_SCENARIOS.items():
    ann = CAGR_1X * edge
    print(f"\n{'#' * 88}\nEDGE SCENARIO: {scen}  (1x annual mean {ann:+.1%}, "
          f"Sharpe ~{ann / VOL_1X:.2f})\n{'#' * 88}")
    for name, cfg in PRESETS.items():
        run_preset(name, cfg, edge)

print("\nNOTES:")
print(" • Fees are approximate list prices — edit PRESETS before trusting $ EV.")
print(" • FundedNext daily loss is balance-based & intraday; the 80% buffer models that.")
print(" • Passing fast ≠ surviving funded: the funded column already includes the")
print("   dd-throttle. Run the challenge at the optimizer's multiplier, then drop")
print("   RISK_SCALE to ~1x (throttled) once funded.")
print(" • If every EV is negative in the 'weak' scenario, do NOT farm challenges")
print("   until live paper results confirm the edge (see FINDINGS.md freeze rule).")
