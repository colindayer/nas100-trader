"""Multi-field asset classification. NEVER from broker folder names alone.

The v2 probe classified from `path` first and put US100.cash and US500.cash into OTHER,
because FTMO's folder names do not contain "INDEX". 73 of 166 symbols landed in OTHER and the
trend-suitable count was meaningless as a result.

This classifier scores EVERY available field and records which evidence fired, so a
misclassification is diagnosable rather than mysterious. It must survive a broker renaming its
folders, because brokers do that without notice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

AssetClass = str  # BOND EQUITY_INDEX FX METAL ENERGY AGRICULTURAL CRYPTO EQUITY RATE UNKNOWN

# Index roots seen across MT5 brokers. Matched as a WHOLE TOKEN so "US100" hits but "US100X"
# is checked by the other rules too rather than silently accepted.
INDEX_ROOTS = [
    "US30", "US100", "US500", "US2000", "USTEC", "NAS100", "NDX", "SPX", "SP500", "DJI", "DJ30",
    "GER30", "GER40", "DAX", "DE30", "DE40", "UK100", "FTSE", "FRA40", "CAC40", "EU50", "STOXX",
    "ESP35", "SPA35", "IBEX", "ITA40", "MIB", "SUI20", "SMI", "NETH25", "AEX",
    "JP225", "NIKKEI", "HK50", "HSI", "AUS200", "ASX200", "CHINA50", "CN50", "SING30",
    "INDIA50", "NIFTY", "BRA50", "VIX",
]
BOND_ROOTS = ["BUND", "BOBL", "SCHATZ", "BUXL", "GILT", "JGB", "BTP", "OAT", "UST", "TNOTE",
              "TBOND", "T-NOTE", "T-BOND", "US10Y", "US02Y", "US30Y", "TREASURY"]
METAL_ROOTS = ["XAU", "XAG", "XPT", "XPD", "GOLD", "SILVER", "PLATINUM", "PALLADIUM",
               "COPPER", "XCU", "ALUMIN", "ZINC", "NICKEL"]
ENERGY_ROOTS = ["WTI", "BRENT", "USOIL", "UKOIL", "CRUDE", "NGAS", "NATGAS", "NATURALGAS",
                "HEATOIL", "GASOIL", "GASOLINE", "OIL"]
AGRI_ROOTS = ["WHEAT", "CORN", "SOYBEAN", "SOYMEAL", "SOYOIL", "COCOA", "COFFEE", "SUGAR",
              "COTTON", "RICE", "OATS", "LUMBER", "CATTLE", "HOGS", "ORANGE"]
CRYPTO_ROOTS = ["BTC", "ETH", "XRP", "LTC", "BCH", "ADA", "SOL", "DOGE", "DOT", "LINK", "AVAX",
                "MATIC", "BNB", "TRX", "SHIB", "UNI", "ATOM", "XLM", "ETC", "FIL", "NEAR"]
FX_CCY = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "SEK", "NOK", "DKK", "PLN",
          "HUF", "CZK", "TRY", "ZAR", "MXN", "SGD", "HKD", "CNH", "THB", "ILS", "RUB"}

CALC_INDEX = {"CFDINDEX"}
CALC_FX = {"FOREX", "FOREX_NO_LEV"}


@dataclass
class Verdict:
    asset_class: AssetClass
    confidence: float
    evidence: list = field(default_factory=list)


def _tok(s: str) -> set:
    """Tokenise a symbol: US100.cash -> {US100, CASH}; XAUUSD stays whole for pair splitting."""
    return set(re.split(r"[^A-Z0-9]+", (s or "").upper())) - {""}


def _root_hit(name: str, roots) -> str | None:
    up = (name or "").upper()
    toks = _tok(name)
    for r in roots:
        if r in toks:
            return r
    # substring fallback, longest root first so BRENT beats no-match and USOIL beats OIL
    for r in sorted(roots, key=len, reverse=True):
        if r in up:
            return r
    return None


def _is_fx_pair(name: str, base: str, profit: str) -> bool:
    """Genuine 6-letter pair of two known currencies, corroborated by base/profit fields."""
    up = re.sub(r"[^A-Z]", "", (name or "").upper())
    if len(up) >= 6:
        a, b = up[:3], up[3:6]
        if a in FX_CCY and b in FX_CCY and a != b:
            return True
    return bool(base in FX_CCY and profit in FX_CCY and base != profit
                and (base in up and profit in up))


def classify(symbol: str, description: str = "", path: str = "", calc_mode: str = "",
             currency_base: str = "", currency_profit: str = "", contract_size: float = 0.0,
             sector: str = "", exchange: str = "") -> Verdict:
    """Score every field. Order matters only for ties; each rule states its own evidence."""
    ev, scores = [], {}

    def add(cls, w, why):
        scores[cls] = scores.get(cls, 0.0) + w
        ev.append(f"{cls}+{w:.1f}: {why}")

    up_desc = (description or "").upper()
    up_path = (path or "").upper()
    cm = (calc_mode or "").upper()

    # ---- BOND. Checked first: a bond named "UST10Y" must not be caught by an FX rule.
    if (r := _root_hit(symbol, BOND_ROOTS)):
        add("BOND", 3.0, f"symbol root {r}")
    if any(k in up_desc for k in ("BOND", "TREASURY", "GILT", "BUND", "NOTE", "YIELD")):
        add("BOND", 2.0, "description mentions bond/treasury")
    if "BOND" in up_path or "RATE" in up_path:
        add("BOND", 1.0, "path")

    # ---- EQUITY INDEX. The v2 failure mode: must NOT depend on the folder name.
    if (r := _root_hit(symbol, INDEX_ROOTS)):
        add("EQUITY_INDEX", 3.0, f"symbol root {r}")
    if any(k in up_desc for k in ("INDEX", "INDICE", "AVERAGE", "COMPOSITE", "100 ", "500 ",
                                  "NASDAQ", "S&P", "DOW", "FTSE", "DAX", "NIKKEI", "HANG SENG")):
        add("EQUITY_INDEX", 2.0, "description mentions an index")
    if cm in CALC_INDEX:
        add("EQUITY_INDEX", 2.0, f"calc_mode {cm}")
    if any(k in up_path for k in ("INDIC", "INDEX", "CASH INDEX")):
        add("EQUITY_INDEX", 1.0, "path")
    # an index CFD quotes and settles in one currency and has no FX-style base pair
    if currency_base and currency_base == currency_profit and currency_base in FX_CCY \
            and not _is_fx_pair(symbol, currency_base, currency_profit):
        add("EQUITY_INDEX", 0.5, "base==profit currency, not an FX pair")

    # ---- METAL / ENERGY / AGRI
    if (r := _root_hit(symbol, METAL_ROOTS)):
        add("METAL", 3.0, f"symbol root {r}")
    if any(k in up_desc for k in ("GOLD", "SILVER", "PLATIN", "PALLAD", "COPPER")):
        add("METAL", 2.0, "description")
    if (r := _root_hit(symbol, ENERGY_ROOTS)):
        add("ENERGY", 3.0, f"symbol root {r}")
    if any(k in up_desc for k in ("OIL", "CRUDE", "BRENT", "GAS", "GASOLINE")):
        add("ENERGY", 2.0, "description")
    if (r := _root_hit(symbol, AGRI_ROOTS)):
        add("AGRICULTURAL", 3.0, f"symbol root {r}")
    if any(k in up_desc for k in ("WHEAT", "CORN", "SOY", "COCOA", "COFFEE", "SUGAR", "COTTON")):
        add("AGRICULTURAL", 2.0, "description")

    # ---- CRYPTO
    if (r := _root_hit(symbol, CRYPTO_ROOTS)):
        add("CRYPTO", 3.0, f"symbol root {r}")
    if any(k in up_desc for k in ("BITCOIN", "ETHEREUM", "CRYPTO", "TOKEN")):
        add("CRYPTO", 2.0, "description")
    if "CRYPT" in up_path:
        add("CRYPTO", 1.5, "path")

    # ---- FX. Requires a genuine currency pair, so XAUUSD is not caught (XAU is not a currency).
    if _is_fx_pair(symbol, currency_base, currency_profit):
        add("FX", 3.0, "6-letter pair of two known currencies")
    if cm in CALC_FX:
        add("FX", 1.5, f"calc_mode {cm}")
    if any(k in up_path for k in ("FOREX", "CURRENC")):
        add("FX", 1.0, "path")

    # ---- EQUITY (single names)
    if cm.startswith("EXCH_STOCKS") or "STOCK" in up_path or "SHARE" in up_path:
        add("EQUITY", 2.5, "calc_mode/path indicates a single stock")
    if sector and sector.upper() not in ("", "UNDEFINED", "NONE"):
        add("EQUITY", 1.0, f"sector {sector}")
    if exchange and exchange.upper() not in ("", "NONE"):
        add("EQUITY", 0.5, f"exchange {exchange}")

    if not scores:
        return Verdict("UNKNOWN", 0.0, ["no rule fired"])
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    return Verdict(best, scores[best] / total if total else 0.0,
                   [e for e in ev if e.startswith(best)] +
                   [f"(competing: {k}={v:.1f})" for k, v in sorted(scores.items(),
                                                                   key=lambda kv: -kv[1])
                    if k != best])
