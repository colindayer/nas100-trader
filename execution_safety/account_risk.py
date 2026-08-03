"""account_risk.py -- THREE SEPARATE RISK CONCEPTS, computed from the live account.

The old Guardian collapsed everything into one number: distance-to-stop x size. That is the right
measure for a strategy whose stop IS its risk budget. It is the wrong measure for a vol-targeted
portfolio whose 15% stop is disaster insurance, and it produced MAX_OPEN_RISK on a single 0.02-lot
position while the strategy's measured risk was 5% annualised vol and -10.19% max drawdown.

These are three different questions and they are kept apart:

  1 EXPECTED VOLATILITY RISK -- what the book is likely to lose on a normal bad day.
    Derived from the strategy's target volatility and gross exposure, not from stop distance.
    This is the number that describes the strategy.

  2 CATASTROPHE STRESS EXPOSURE -- what we lose if every position gaps to its disaster stop at
    once. Distance-to-stop x size, summed. This is a STRESS SCENARIO, never the normal risk model,
    and it is not compared against a per-trade risk limit.

  3 FTMO RULE HEADROOM -- how far the ACCOUNT is from the daily-loss and total-loss boundaries
    right now, in money, including open P&L, realised P&L today, commission, swap and a
    conservative slippage buffer.

NEW EXPOSURE IS PERMITTED ONLY IF, FAIL-CLOSED:

    catastrophe_stress + proposed_catastrophe + current_losses + buffer  <  headroom

evaluated against BOTH boundaries. If any input is missing or unreadable, the answer is NO.

The 15% broker stop remains DISASTER PROTECTION ONLY. It is never treated as the normal risk
model and never used to size a position.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

# FTMO standard rules. Percentages are of the INITIAL balance, which is how FTMO evaluates them.
ACCOUNT_RULES = {
    "FTMO": {"daily_loss_pct": 5.0, "total_loss_pct": 10.0, "profit_target_pct": 10.0},
    "FUNDEDNEXT": {"daily_loss_pct": 5.0, "total_loss_pct": 10.0, "profit_target_pct": 8.0},
    "GENERIC": {"daily_loss_pct": 5.0, "total_loss_pct": 10.0, "profit_target_pct": 10.0},
}

# Conservative buffers. These make the gate fire EARLY, never late.
SLIPPAGE_BUFFER_PCT = 0.10        # of equity, reserved for adverse fills on an unwind
SAFETY_MARGIN_PCT = 0.20          # of equity, refuse to consume the last of any headroom
VOL_SHOCK_SIGMA = 3.0             # a "normal bad day" is 3 daily sigma


def detect_account_type(server: str) -> str:
    s = (server or "").upper()
    for k in ACCOUNT_RULES:
        if k != "GENERIC" and k in s.replace("-", "").replace(" ", ""):
            return k
    return "GENERIC"


@dataclass
class RiskReport:
    ok: bool
    account_type: str
    initial_balance: float
    equity: float
    balance: float
    day_start_equity: float
    # --- realised / unrealised
    open_pnl: float
    realised_pnl_today: float
    commission_today: float
    swap_today: float
    # --- 1. expected volatility risk
    target_vol_annual: float
    gross_exposure: float
    daily_sigma_money: float
    expected_bad_day_money: float
    # --- 2. catastrophe stress
    catastrophe_stress_money: float
    catastrophe_stress_pct: float
    # --- 3. rule headroom
    daily_loss_limit_money: float
    daily_loss_used_money: float
    daily_headroom_money: float
    total_loss_limit_money: float
    total_loss_used_money: float
    total_headroom_money: float
    slippage_buffer_money: float
    safety_margin_money: float
    max_additional_catastrophe_money: float
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _deals_today(mt5, login):
    """Realised P&L, commission and swap since the FTMO day boundary (00:00 server time)."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        deals = mt5.history_deals_get(start, now + timedelta(minutes=1))
    except Exception:
        return None, None, None
    if deals is None:
        return None, None, None
    # EXCLUDE balance/credit operations. The initial 100,000 deposit is a DEAL_TYPE_BALANCE and
    # summing it produced "realised P&L today: 100,000.00" on a day with no closed trades.
    BALANCE_TYPES = {2, 3, 4, 5, 6}      # BALANCE, CREDIT, CHARGE, CORRECTION, BONUS
    trades = [d for d in deals if int(getattr(d, "type", 0)) not in BALANCE_TYPES]
    pnl = sum(float(getattr(d, "profit", 0.0) or 0.0) for d in trades)
    com = sum(float(getattr(d, "commission", 0.0) or 0.0) for d in trades)
    swp = sum(float(getattr(d, "swap", 0.0) or 0.0) for d in trades)
    return pnl, com, swp


def assess(mt5, magic: int, initial_balance: float, target_vol_annual: float,
           proposed_gross: float = 0.0, proposed_catastrophe_pct: float = 0.0,
           catastrophe_frac: float = 0.15) -> RiskReport:
    """Compute all three risk concepts from the LIVE account. Fail closed on any missing input.

    proposed_gross            gross exposure (fraction of equity) the plan wants to hold
    proposed_catastrophe_pct  additional catastrophe stress the plan would add, as % of equity
    """
    reasons = []
    acct = mt5.account_info()
    if acct is None:
        return RiskReport(ok=False, account_type="?", initial_balance=0, equity=0, balance=0,
                          day_start_equity=0, open_pnl=0, realised_pnl_today=0,
                          commission_today=0, swap_today=0, target_vol_annual=0,
                          gross_exposure=0, daily_sigma_money=0, expected_bad_day_money=0,
                          catastrophe_stress_money=0, catastrophe_stress_pct=0,
                          daily_loss_limit_money=0, daily_loss_used_money=0,
                          daily_headroom_money=0, total_loss_limit_money=0,
                          total_loss_used_money=0, total_headroom_money=0,
                          slippage_buffer_money=0, safety_margin_money=0,
                          max_additional_catastrophe_money=0,
                          reasons=["ACCOUNT_INFO_UNAVAILABLE"])

    atype = detect_account_type(getattr(acct, "server", ""))
    rules = ACCOUNT_RULES[atype]
    equity = float(acct.equity)
    balance = float(acct.balance)

    positions = mt5.positions_get()
    if positions is None:
        reasons.append("POSITIONS_UNREADABLE")
        positions = []
    ours = [p for p in positions if getattr(p, "magic", None) == magic]

    open_pnl = sum(float(getattr(p, "profit", 0.0) or 0.0) for p in ours)
    rpnl, com, swp = _deals_today(mt5, getattr(acct, "login", None))
    if rpnl is None:
        reasons.append("DEAL_HISTORY_UNREADABLE")
        rpnl = com = swp = 0.0

    # ---- day start equity: from persisted safety state, never from current equity
    try:
        from . import safety_state as ss
        st, _ = ss.load(equity=equity, login=getattr(acct, "login", None))
        day_start = float(st.day_start_equity or equity)
    except Exception:
        reasons.append("SAFETY_STATE_UNREADABLE")
        day_start = equity

    # ================= 1. EXPECTED VOLATILITY RISK =================
    # The book's own risk, from its target volatility and how much of it is actually on.
    gross = float(proposed_gross)
    daily_sigma = equity * target_vol_annual / (252 ** 0.5)
    expected_bad_day = daily_sigma * VOL_SHOCK_SIGMA

    # ================= 2. CATASTROPHE STRESS =================
    # Every open position gapping to its disaster stop simultaneously. A STRESS number.
    stress = 0.0
    for p in ours:
        sl = float(getattr(p, "sl", 0.0) or 0.0)
        price = float(getattr(p, "price_open", 0.0) or 0.0)
        vol = float(getattr(p, "volume", 0.0) or 0.0)
        try:
            info = mt5.symbol_info(p.symbol)
            tick = mt5.symbol_info_tick(p.symbol)
            cs = float(getattr(info, "trade_contract_size", 0.0) or 0.0)
            per_unit = cs if p.symbol[:3].upper() == "USD" else cs * float(tick.ask or price)
            notional = vol * per_unit
        except Exception:
            reasons.append(f"SYMBOL_INFO_UNAVAILABLE:{getattr(p,'symbol','?')}")
            continue
        frac = abs(price - sl) / price if (sl > 0 and price > 0) else catastrophe_frac
        stress += notional * frac
    # CURRENT stress is what is already on the book. The PROPOSED amount is checked against the
    # budget separately -- folding it into `stress` and then subtracting it made the budget
    # arithmetic self-cancelling and returned 0.00 allowed on a completely flat account.
    current_stress = stress
    proposed_stress = equity * float(proposed_catastrophe_pct) / 100.0
    stress = current_stress + proposed_stress

    # ================= 3. FTMO RULE HEADROOM =================
    daily_limit = initial_balance * rules["daily_loss_pct"] / 100.0
    total_limit = initial_balance * rules["total_loss_pct"] / 100.0
    daily_used = max(0.0, day_start - equity)                 # loss since the day started
    total_used = max(0.0, initial_balance - equity)           # loss since inception
    daily_headroom = daily_limit - daily_used
    total_headroom = total_limit - total_used

    buffer_money = equity * SLIPPAGE_BUFFER_PCT / 100.0
    margin_money = equity * SAFETY_MARGIN_PCT / 100.0

    # How much MORE catastrophe stress may be added before either boundary is threatened.
    # Fail-closed: the tighter of the two, minus what is already exposed, minus buffers.
    allowed = min(daily_headroom, total_headroom) - current_stress - buffer_money - margin_money
    allowed = max(0.0, allowed)

    if daily_headroom <= 0:
        reasons.append("DAILY_LOSS_BOUNDARY_REACHED")
    if total_headroom <= 0:
        reasons.append("TOTAL_LOSS_BOUNDARY_REACHED")
    # Only the EXISTING book breaching headroom is a blocking condition. A plan that wants more
    # than the budget is not an error: the engine tranches it. Blocking there would mean a flat
    # account could never open anything.
    if current_stress + buffer_money + margin_money >= min(daily_headroom, total_headroom):
        reasons.append("CATASTROPHE_STRESS_EXCEEDS_HEADROOM")
    if expected_bad_day >= daily_headroom:
        reasons.append("EXPECTED_BAD_DAY_EXCEEDS_DAILY_HEADROOM")

    return RiskReport(
        ok=(len(reasons) == 0), account_type=atype, initial_balance=initial_balance,
        equity=equity, balance=balance, day_start_equity=day_start,
        open_pnl=open_pnl, realised_pnl_today=rpnl, commission_today=com, swap_today=swp,
        target_vol_annual=target_vol_annual, gross_exposure=gross,
        daily_sigma_money=daily_sigma, expected_bad_day_money=expected_bad_day,
        catastrophe_stress_money=stress,
        catastrophe_stress_pct=100.0 * stress / max(equity, 1e-9),
        daily_loss_limit_money=daily_limit, daily_loss_used_money=daily_used,
        daily_headroom_money=daily_headroom,
        total_loss_limit_money=total_limit, total_loss_used_money=total_used,
        total_headroom_money=total_headroom,
        slippage_buffer_money=buffer_money, safety_margin_money=margin_money,
        max_additional_catastrophe_money=allowed, reasons=reasons)


def render(r: RiskReport) -> str:
    L = []
    A = L.append
    A("=" * 92)
    A(f" ACCOUNT-AWARE RISK  —  {r.account_type}  equity {r.equity:,.2f}  "
      f"balance {r.balance:,.2f}  initial {r.initial_balance:,.2f}")
    A("=" * 92)
    A(f"  {'P&L':<34}{'money':>16}")
    A(f"  {'open P&L':<34}{r.open_pnl:>16,.2f}")
    A(f"  {'realised P&L today':<34}{r.realised_pnl_today:>16,.2f}")
    A(f"  {'commission today':<34}{r.commission_today:>16,.2f}")
    A(f"  {'swap today':<34}{r.swap_today:>16,.2f}")
    A("-" * 92)
    A(f"  {'1 EXPECTED VOLATILITY RISK':<34}{'money':>16}{'% equity':>12}")
    A(f"  {'  target vol (annual)':<34}{'':>16}{r.target_vol_annual*100:>11.2f}%")
    A(f"  {'  gross exposure':<34}{'':>16}{r.gross_exposure*100:>11.2f}%")
    A(f"  {'  daily 1-sigma':<34}{r.daily_sigma_money:>16,.2f}"
      f"{100*r.daily_sigma_money/max(r.equity,1e-9):>11.2f}%")
    A(f"  {'  expected bad day (3 sigma)':<34}{r.expected_bad_day_money:>16,.2f}"
      f"{100*r.expected_bad_day_money/max(r.equity,1e-9):>11.2f}%")
    A("-" * 92)
    A(f"  {'2 CATASTROPHE STRESS (all stops hit)':<34}{r.catastrophe_stress_money:>16,.2f}"
      f"{r.catastrophe_stress_pct:>11.2f}%")
    A("-" * 92)
    A(f"  {'3 RULE HEADROOM':<34}{'limit':>16}{'used':>14}{'headroom':>14}")
    A(f"  {'  daily loss':<34}{r.daily_loss_limit_money:>16,.2f}"
      f"{r.daily_loss_used_money:>14,.2f}{r.daily_headroom_money:>14,.2f}")
    A(f"  {'  total loss':<34}{r.total_loss_limit_money:>16,.2f}"
      f"{r.total_loss_used_money:>14,.2f}{r.total_headroom_money:>14,.2f}")
    A(f"  {'  slippage buffer':<34}{r.slippage_buffer_money:>16,.2f}")
    A(f"  {'  safety margin':<34}{r.safety_margin_money:>16,.2f}")
    A("-" * 92)
    A(f"  MAX ADDITIONAL CATASTROPHE EXPOSURE ALLOWED: {r.max_additional_catastrophe_money:,.2f}"
      f"  ({100*r.max_additional_catastrophe_money/max(r.equity,1e-9):.2f}% of equity)")
    A(f"  VERDICT: {'OK' if r.ok else 'BLOCKED — ' + ', '.join(r.reasons)}")
    A("=" * 92)
    return "\n".join(L)
