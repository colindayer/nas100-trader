"""Broker intelligence layer tests, using the REAL symbol names from the 2026-08-05 probes.

The v2 classifier put US100.cash and US500.cash into OTHER because it keyed on broker folder
names. 73 of 166 FTMO symbols landed in OTHER and the trend-suitable count was meaningless.
These cases are pinned here so that failure cannot recur silently.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from broker.classify import classify
from broker.financing import (swap_usd_per_lot_night, point_value_per_lot, financing_drag)


def test_classifier_real_ftmo_symbols():
    # (symbol, description, path, calc_mode, base, profit, expected)
    CASES = [
        # THE v2 FAILURES — folder name gives no hint, must classify from symbol+desc anyway
        ("US100.cash", "US Tech 100 Index", r"CFD\Cash", "CFDLEVERAGE", "USD", "USD",
         "EQUITY_INDEX"),
        ("US500.cash", "US 500 Index", r"CFD\Cash", "CFDLEVERAGE", "USD", "USD", "EQUITY_INDEX"),
        # deliberately hostile: folder renamed to something meaningless
        ("GER40.cash", "Germany 40", r"Misc\Group7", "CFDLEVERAGE", "EUR", "EUR",
         "EQUITY_INDEX"),
        ("JP225.cash", "Japan 225", "", "", "JPY", "JPY", "EQUITY_INDEX"),
        # metals — XAUUSD must NOT be FX even though it ends in USD
        ("XAUUSD", "Gold vs US Dollar", r"CFD\Metals", "CFD", "XAU", "USD", "METAL"),
        ("XAGUSD", "Silver vs US Dollar", r"CFD\Metals", "CFD", "XAG", "USD", "METAL"),
        ("XCUUSD", "Copper", r"CFD\Metals", "CFD", "XCU", "USD", "METAL"),
        # energy
        ("UKOIL.cash", "Brent Crude Oil", r"CFD\Energy", "CFD", "USD", "USD", "ENERGY"),
        ("USOIL.cash", "WTI Crude Oil", r"CFD\Energy", "CFD", "USD", "USD", "ENERGY"),
        ("NATGAS.cash", "Natural Gas", "", "CFD", "USD", "USD", "ENERGY"),
        # agriculturals
        ("WHEAT.c", "Wheat", "", "CFD", "USD", "USD", "AGRICULTURAL"),
        ("COCOA.c", "Cocoa", "", "CFD", "USD", "USD", "AGRICULTURAL"),
        # FX — genuine pairs only
        ("EURUSD", "Euro vs US Dollar", r"Forex\Majors", "FOREX", "EUR", "USD", "FX"),
        ("USDJPY", "US Dollar vs Yen", r"Forex\Majors", "FOREX", "USD", "JPY", "FX"),
        # crypto
        ("BTCUSD", "Bitcoin vs US Dollar", r"Crypto", "CFD", "BTC", "USD", "CRYPTO"),
        # bonds — none on FTMO, but Pepperstone has them and the classifier must handle them
        ("BUND", "Euro Bund", r"CFD\Bonds", "CFD", "EUR", "EUR", "BOND"),
        ("UST10Y", "US 10 Year Treasury Note", "", "CFD", "USD", "USD", "BOND"),
    ]
    bad = []
    for sym, desc, path, cm, base, prof, want in CASES:
        v = classify(sym, desc, path, cm, base, prof)
        if v.asset_class != want:
            bad.append(f"{sym}: got {v.asset_class} want {want} | {v.evidence[:2]}")
    assert not bad, "classifier failures:\n  " + "\n  ".join(bad)
    print(f"  classifier: {len(CASES)}/{len(CASES)} real symbols correct")

    # the specific v2 regression, asserted alone so the failure message is unambiguous
    v = classify("US100.cash", "US Tech 100 Index", r"CFD\Cash", "CFDLEVERAGE", "USD", "USD")
    assert v.asset_class == "EQUITY_INDEX", f"US100.cash -> {v.asset_class} (v2 said OTHER)"
    assert v.confidence > 0.5, f"low confidence {v.confidence:.2f}"
    print(f"  US100.cash -> EQUITY_INDEX conf {v.confidence:.2f}  (v2 said OTHER)")


def test_classifier_survives_folder_rename():
    """Brokers rename folders without notice. Classification must not depend on that."""
    for path in ("", r"CFD\Cash", r"Weird\Group12", "ZZZ", r"Forex\Exotics"):
        v = classify("US100.cash", "US Tech 100 Index", path, "CFDLEVERAGE", "USD", "USD")
        assert v.asset_class == "EQUITY_INDEX", f"path={path!r} broke it -> {v.asset_class}"
    print("  classification is stable across 5 different/absent folder names")


def test_financing_points_conversion():
    """US100.cash swap_long = -559.07 POINTS. Raw points are not decision-grade."""
    pv = point_value_per_lot(tick_value=1.0, tick_size=0.1, point=0.1)
    assert abs(pv - 1.0) < 1e-9, pv
    f = swap_usd_per_lot_night(-559.07, -56.72, "POINTS",
                               tick_value=1.0, tick_size=0.1, point=0.1)
    assert f.reliable and abs(f.long_usd_per_lot_night + 559.07) < 1e-6
    print(f"  US100.cash POINTS -> ${f.long_usd_per_lot_night:,.2f}/lot/night long")

    # cannot convert without tick data -> must be flagged unreliable, never guessed
    bad = swap_usd_per_lot_night(-559.07, -56.72, "POINTS", tick_value=0, tick_size=0, point=0)
    assert not bad.reliable and bad.long_usd_per_lot_night != bad.long_usd_per_lot_night
    print("  missing tick data -> reliable=False, NaN (not a guess)")

    # Pepperstone used INT_CURRENT: annual percent of notional
    p = swap_usd_per_lot_night(-6.12, 1.02, "INT_CURRENT", contract_size=1.0, price=20000.0)
    exp = 20000.0 * -6.12 / 100.0 / 365.0
    assert p.reliable and abs(p.long_usd_per_lot_night - exp) < 1e-9
    print(f"  Pepperstone INT_CURRENT -6.12%/yr -> ${p.long_usd_per_lot_night:.4f}/lot/night")

    unknown = swap_usd_per_lot_night(1, 1, "REOPEN_BID")
    assert not unknown.reliable
    print("  unhandled swap_mode -> reliable=False rather than a wrong number")


def test_financing_drag_counts_weekend_nights():
    """5 trading days is 7 swap-nights. Ignoring weekends understates cost ~40%."""
    d = financing_drag(-10.0, lots=1.0, account_equity=100_000.0)
    assert abs(d["5d"] - (-10.0 * 7.0 / 100_000.0)) < 1e-12, d
    assert d["120d"] < d["60d"] < d["20d"] < d["5d"] < 0
    print(f"  drag on $100k, $10/night: 5d {d['5d']:.4%}  20d {d['20d']:.4%}  "
          f"60d {d['60d']:.4%}  120d {d['120d']:.4%}")


if __name__ == "__main__":
    test_classifier_real_ftmo_symbols()
    test_classifier_survives_folder_rename()
    test_financing_points_conversion()
    test_financing_drag_counts_weekend_nights()
    print("\nPASS — broker intelligence layer")


def test_bar_request_stays_below_maxbars():
    """MT5 returns None when count == terminal maxbars. That single boundary made both probes
    report 0 bars for all 166 FTMO symbols, when XAUUSD actually serves 5000+ on the first call.

    Verified on FTMO-Demo 2026-08-09: maxbars=100000, request 100000 -> None,
    request 5000 -> 5000 bars, err=(1,'Success').
    """
    import re
    src = (Path(__file__).resolve().parents[1] / "scripts" / "broker_probe.py").read_text()
    caps = [int(m) for m in re.findall(r"MAX_BARS_(?:D1|H1)\s*=\s*(\d+)", src)]
    assert len(caps) == 2, "bar-count caps are gone"
    assert all(c < 100000 for c in caps), f"caps {caps} not below the typical maxbars of 100000"
    assert all(c <= 10000 for c in caps), (
        f"caps {caps} are large enough to force a multi-year server download per symbol; "
        "that blocked the probe at near-zero CPU on 166 cold symbols")
    assert "0, 100000)" not in src, "a hardcoded 100000-bar request is back in the probe"
    assert "mb - 1" in src, "cap is not clamped relative to the live terminal maxbars"
    print(f"  bar requests capped at D1={caps[0]:,} H1={caps[1]:,}, clamped to maxbars-1 "
          f"(the boundary that returned None; large values blocked on downloads)")
