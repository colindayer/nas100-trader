"""Swap points -> economic cost in account currency. Raw broker points are not decision-grade.

The v2 probe reported US100.cash swap_long = -559.07 and that number is uninterpretable on its
own: it is POINTS PER LOT PER NIGHT, and a point is worth a different amount on every symbol.
Two symbols with identical swap points can differ 100x in real cost.

MT5 SWAP_MODE semantics implemented here:
  POINTS            swap is in symbol points -> multiply by the value of one point per lot
  SYMBOL_CURRENCY   swap is already money per lot, in the symbol's base currency
  MARGIN_CURRENCY   money per lot, in margin currency
  DEPOSIT_CURRENCY  money per lot, in the account's currency -- used directly
  INT_CURRENT /     swap is an ANNUAL PERCENT of position value (Pepperstone used this)
  INT_OPEN
Anything else is returned as UNKNOWN rather than guessed at, because a wrong financing number
is worse than an absent one.
"""
from __future__ import annotations

from dataclasses import dataclass

MONEY_MODES = {"SYMBOL_CURRENCY", "MARGIN_CURRENCY", "DEPOSIT_CURRENCY", "SYMBOL_CCY",
               "MARGIN_CCY", "DEPOSIT_CCY"}
PERCENT_MODES = {"INT_CURRENT", "INT_OPEN", "INTEREST_CURRENT", "INTEREST_OPEN"}


@dataclass
class Financing:
    long_usd_per_lot_night: float
    short_usd_per_lot_night: float
    basis: str            # how it was derived
    reliable: bool        # False -> do not put this in a backtest


def point_value_per_lot(tick_value: float, tick_size: float, point: float) -> float:
    """Money per 1 point of price movement, per 1.0 lot, in the account currency.

    tick_value is money per tick_size of movement, so scale by point/tick_size.
    """
    if not tick_size or tick_size <= 0 or not point or point <= 0:
        return float("nan")
    return float(tick_value) * (float(point) / float(tick_size))


def swap_usd_per_lot_night(swap_long: float, swap_short: float, swap_mode: str,
                           tick_value: float = 0.0, tick_size: float = 0.0, point: float = 0.0,
                           contract_size: float = 0.0, price: float = 0.0) -> Financing:
    mode = (swap_mode or "").upper()

    if mode in MONEY_MODES:
        return Financing(float(swap_long), float(swap_short),
                         f"{mode}: already money per lot", True)

    if mode == "POINTS":
        pv = point_value_per_lot(tick_value, tick_size, point)
        if pv != pv:  # NaN
            return Financing(float("nan"), float("nan"),
                             "POINTS but tick_size/point missing -> cannot convert", False)
        return Financing(float(swap_long) * pv, float(swap_short) * pv,
                         f"POINTS x point_value {pv:.6f}/lot", True)

    if mode in PERCENT_MODES:
        notional = float(contract_size) * float(price)
        if notional <= 0:
            return Financing(float("nan"), float("nan"),
                             f"{mode} but contract_size/price missing -> cannot convert", False)
        # annual percent -> per night
        return Financing(notional * float(swap_long) / 100.0 / 365.0,
                         notional * float(swap_short) / 100.0 / 365.0,
                         f"{mode}: annual % of notional {notional:,.0f}", True)

    return Financing(float("nan"), float("nan"), f"unhandled swap_mode {mode!r}", False)


def financing_drag(usd_per_lot_night: float, lots: float, account_equity: float,
                   horizons=(5, 20, 60, 120), rollover3days_weekday: int = 3) -> dict:
    """Cost as a fraction of equity over holding horizons.

    Calendar nights, not trading days: a position held over a weekend is charged for it, and
    MT5 books a TRIPLE swap on one weekday (default Wednesday) to cover it. 5 trading days is
    therefore 7 swap-nights, not 5. Ignoring this understates cost by ~40%.
    """
    if usd_per_lot_night != usd_per_lot_night or account_equity <= 0:
        return {f"{h}d": float("nan") for h in horizons}
    out = {}
    for h in horizons:
        weeks = h / 5.0
        nights = h + 2.0 * weeks          # weekend nights
        total = usd_per_lot_night * lots * nights
        out[f"{h}d"] = total / account_equity
    return out
