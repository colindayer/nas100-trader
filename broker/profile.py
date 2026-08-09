"""BrokerProfile — what strategies consume instead of querying MT5.

A strategy asks the profile what it can trade, what history exists, and what financing costs.
It never calls MetaTrader5 itself. That makes strategies testable off-VPS, comparable across
brokers, and honest about the fact that THE BROKER IS PART OF THE EXPERIMENTAL ENVIRONMENT.

Loads from the CSV/JSON emitted by scripts/broker_probe.py. No MT5 import anywhere in this file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import pandas as pd

from broker.classify import classify
from broker.financing import swap_usd_per_lot_night, financing_drag

# Research-capability thresholds in D1 bars. "Tradable" and "researchable" are DIFFERENT
# properties and this project conflated them once already.
SIGNAL_MIN_D1 = 300      # a 252-day signal plus warmup -- can TRADE the strategy
VALID_5Y_D1 = 1260       # ~5 years -- minimal out-of-sample validation
VALID_10Y_D1 = 2520      # ~10 years -- validation spanning more than one regime
TREND_MIN_D1_BARS = SIGNAL_MIN_D1


@dataclass
class SymbolSpec:
    symbol: str
    asset_class: str
    description: str = ""
    trade_mode: str = ""
    execution_mode: str = ""
    contract_size: float = 0.0
    tick_size: float = 0.0
    tick_value: float = 0.0
    point: float = 0.0
    digits: int = 0
    volume_min: float = 0.0
    volume_max: float = 0.0
    volume_step: float = 0.0
    spread_price: float = 0.0
    swap_long: float = 0.0
    swap_short: float = 0.0
    swap_mode: str = ""
    margin_initial: float = 0.0
    d1_bars: int = 0
    d1_from: str = ""
    h1_bars: int = 0
    history_latency_s: float = float("nan")
    price: float = 0.0
    classifier_confidence: float = 0.0

    @property
    def tradable(self) -> bool:
        return self.trade_mode == "FULL"

    @property
    def can_signal_252d(self) -> bool:
        """Enough history to COMPUTE a 252-day signal live. Says nothing about validating it."""
        return self.tradable and self.d1_bars >= SIGNAL_MIN_D1

    @property
    def can_validate_5y(self) -> bool:
        return self.tradable and self.d1_bars >= VALID_5Y_D1

    @property
    def can_validate_10y(self) -> bool:
        return self.tradable and self.d1_bars >= VALID_10Y_D1

    @property
    def trend_suitable(self) -> bool:
        return self.can_signal_252d

    @property
    def data_status(self) -> str:
        """TRADABLE != RESEARCHABLE. A symbol can be fully live and still be useless for
        validation. Copper is live with ~1.7 years of broker history."""
        if not self.tradable or self.d1_bars <= 0:
            return "UNAVAILABLE" if self.d1_bars <= 0 else "METADATA_ONLY"
        if self.d1_bars >= VALID_10Y_D1:
            return "LIVE_AND_LONG_HISTORY"
        if self.d1_bars >= VALID_5Y_D1:
            return "LIVE_LIMITED_HISTORY"
        if self.d1_bars >= SIGNAL_MIN_D1:
            return "LIVE_SIGNAL_ONLY"
        return "METADATA_ONLY"

    def financing(self):
        return swap_usd_per_lot_night(self.swap_long, self.swap_short, self.swap_mode,
                                      self.tick_value, self.tick_size, self.point,
                                      self.contract_size, self.price)


@dataclass
class BrokerProfile:
    broker: str
    server: str
    login: int
    currency: str
    captured_utc: str
    symbols: dict = field(default_factory=dict)     # name -> SymbolSpec

    # ---------------------------------------------------------------- construction
    @classmethod
    def from_csv(cls, csv_path, meta_path=None) -> "BrokerProfile":
        df = pd.read_csv(csv_path)
        meta = {}
        if meta_path and Path(meta_path).exists():
            meta = json.load(open(meta_path))
        syms = {}
        for _, r in df.iterrows():
            v = classify(str(r.get("symbol", "")), str(r.get("description", "")),
                         str(r.get("path", "")), str(r.get("calc_mode", "")),
                         str(r.get("currency_base", "")), str(r.get("currency_profit", "")),
                         float(r.get("contract_size", 0) or 0),
                         str(r.get("sector", "")), str(r.get("exchange", "")))
            s = SymbolSpec(
                symbol=str(r["symbol"]), asset_class=v.asset_class,
                description=str(r.get("description", "")),
                trade_mode=str(r.get("trade_mode", "")),
                execution_mode=str(r.get("execution_mode", "")),
                contract_size=float(r.get("contract_size", 0) or 0),
                tick_size=float(r.get("tick_size", 0) or 0),
                tick_value=float(r.get("tick_value", 0) or 0),
                point=float(r.get("point", 0) or 0), digits=int(r.get("digits", 0) or 0),
                volume_min=float(r.get("volume_min", 0) or 0),
                volume_max=float(r.get("volume_max", 0) or 0),
                volume_step=float(r.get("volume_step", 0) or 0),
                spread_price=float(r.get("spread_price", 0) or 0),
                swap_long=float(r.get("swap_long", 0) or 0),
                swap_short=float(r.get("swap_short", 0) or 0),
                swap_mode=str(r.get("swap_mode", "")),
                margin_initial=float(r.get("margin_initial", 0) or 0),
                d1_bars=int(r.get("d1_bars", 0) or 0), d1_from=str(r.get("d1_from", "")),
                h1_bars=int(r.get("h1_bars", 0) or 0),
                history_latency_s=float(r.get("history_latency_s", float("nan")) or float("nan")),
                price=float(r.get("bid", 0) or 0),
                classifier_confidence=v.confidence)
            syms[s.symbol] = s
        return cls(broker=meta.get("company", "?"), server=meta.get("server", "?"),
                   login=int(meta.get("login", 0) or 0), currency=meta.get("currency", "USD"),
                   captured_utc=meta.get("captured_utc", ""), symbols=syms)

    # ---------------------------------------------------------------- queries
    def by_class(self, cls: str) -> list:
        return [s for s in self.symbols.values() if s.asset_class == cls]

    def asset_classes(self) -> dict:
        out = {}
        for s in self.symbols.values():
            out[s.asset_class] = out.get(s.asset_class, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def tradable(self) -> list:
        return [s for s in self.symbols.values() if s.tradable]

    def trend_universe(self, classes=None) -> list:
        u = [s for s in self.symbols.values() if s.trend_suitable]
        return [s for s in u if s.asset_class in classes] if classes else u

    def missing_classes(self, expected=("BOND", "EQUITY_INDEX", "FX", "METAL", "ENERGY",
                                        "AGRICULTURAL", "CRYPTO")) -> list:
        have = {s.asset_class for s in self.symbols.values() if s.tradable}
        return [c for c in expected if c not in have]

    def capability_report(self) -> dict:
        """What this broker can and cannot support. The 'cannot' half is the important half."""
        tr = self.tradable()
        hist = [s for s in self.symbols.values() if s.d1_bars > 0]
        lat = [s.history_latency_s for s in self.symbols.values()
               if s.history_latency_s == s.history_latency_s]
        return {
            "broker": self.broker, "server": self.server, "login": self.login,
            "currency": self.currency, "captured_utc": self.captured_utc,
            "n_symbols": len(self.symbols), "n_tradable": len(tr),
            "asset_classes": self.asset_classes(),
            "missing_asset_classes": self.missing_classes(),
            "trade_modes": _count(self.symbols.values(), "trade_mode"),
            "execution_modes": _count(self.symbols.values(), "execution_mode"),
            "swap_modes": _count(self.symbols.values(), "swap_mode"),
            "history": {
                "symbols_with_any_d1": len(hist),
                "symbols_d1_ge_1000": len([s for s in self.symbols.values()
                                           if s.d1_bars >= TREND_MIN_D1_BARS]),
                "median_d1_bars": float(pd.Series([s.d1_bars for s in self.symbols.values()])
                                        .median()),
                "earliest_d1": min([s.d1_from for s in hist if s.d1_from], default=""),
                "median_latency_s": float(pd.Series(lat).median()) if lat else None,
                "success_rate": (len(hist) / len(self.symbols)) if self.symbols else 0.0,
            },
            "trend_universe_size": len(self.trend_universe()),
            "data_status": _count(self.symbols.values(), "data_status"),
            "research_capability": {
                "can_signal_252d": len([s for s in self.symbols.values() if s.can_signal_252d]),
                "can_validate_5y": len([s for s in self.symbols.values() if s.can_validate_5y]),
                "can_validate_10y": len([s for s in self.symbols.values() if s.can_validate_10y]),
            },
            "limitations": self._limitations(),
        }

    def _limitations(self) -> list:
        lim = []
        miss = self.missing_classes()
        if miss:
            lim.append(f"NO {', '.join(miss)} — hypotheses requiring these are NOT EVALUABLE "
                       f"on this broker. That is not the same as false.")
        if len(self.trend_universe()) < 10:
            lim.append(f"only {len(self.trend_universe())} symbols have >={TREND_MIN_D1_BARS} "
                       f"D1 bars — breadth studies are history-limited here")
        unrel = [s.symbol for s in self.symbols.values() if not s.financing().reliable]
        if unrel:
            lim.append(f"{len(unrel)} symbols have unconvertible swap "
                       f"(e.g. {', '.join(unrel[:3])}) — financing cannot be modelled")
        low = [s.symbol for s in self.symbols.values() if s.classifier_confidence < 0.5]
        if low:
            lim.append(f"{len(low)} symbols classified with confidence <0.5 — review before use")
        sig = len([s for s in self.symbols.values() if s.can_signal_252d])
        v10 = len([s for s in self.symbols.values() if s.can_validate_10y])
        if sig > v10:
            lim.append(f"{sig} symbols can COMPUTE a 252d signal but only {v10} have 10y of "
                       f"broker history — TRADABLE != RESEARCHABLE. Strategies validated on "
                       f"external reference data cannot be re-validated on this broker's own.")
        return lim

    def frozen_six_financing(self, equity: float, lots: float = 1.0) -> pd.DataFrame:
        """Financing on the six symbols the production portfolio actually holds.

        CRITICAL: financing was ABSENT from every historical backtest of that portfolio. Its
        cost has never been measured, only assumed to be negligible."""
        PATTERNS = {"GOLD": ["XAUUSD"], "SILVER": ["XAGUSD"],
                    "OIL": ["USOIL", "UKOIL", "WTI", "BRENT"], "COPPER": ["XCUUSD", "COPPER"],
                    "NAS100": ["US100", "NAS100", "USTEC"], "SP500": ["US500", "SP500", "SPX"]}
        rows = []
        for leg, pats in PATTERNS.items():
            hits = [s for s in self.symbols.values()
                    if any(p in s.symbol.upper() for p in pats)]
            if not hits:
                rows.append({"leg": leg, "symbol": "NOT FOUND", "reliable": False})
                continue
            s = max(hits, key=lambda x: x.d1_bars)
            f = s.financing()
            dL = financing_drag(f.long_usd_per_lot_night, lots, equity)
            dS = financing_drag(f.short_usd_per_lot_night, lots, equity)
            rows.append({
                "leg": leg, "symbol": s.symbol, "asset_class": s.asset_class,
                "d1_bars": s.d1_bars, "data_status": s.data_status,
                "swap_mode": s.swap_mode, "reliable": f.reliable,
                "long_usd_night": f.long_usd_per_lot_night,
                "short_usd_night": f.short_usd_per_lot_night,
                "long_ann_drag": dL["120d"] * (252 / 120) if dL["120d"] == dL["120d"] else float("nan"),
                "short_ann_drag": dS["120d"] * (252 / 120) if dS["120d"] == dS["120d"] else float("nan"),
                **{f"long_{k}": v for k, v in dL.items()},
                **{f"short_{k}": v for k, v in dS.items()}})
        return pd.DataFrame(rows)

    def financing_table(self, equity: float, lots: float = 1.0) -> pd.DataFrame:
        rows = []
        for s in self.tradable():
            f = s.financing()
            dL = financing_drag(f.long_usd_per_lot_night, lots, equity)
            dS = financing_drag(f.short_usd_per_lot_night, lots, equity)
            rows.append({"symbol": s.symbol, "asset_class": s.asset_class,
                         "swap_mode": s.swap_mode, "reliable": f.reliable,
                         "long_usd_night": f.long_usd_per_lot_night,
                         "short_usd_night": f.short_usd_per_lot_night,
                         **{f"long_drag_{k}": v for k, v in dL.items()},
                         **{f"short_drag_{k}": v for k, v in dS.items()},
                         "basis": f.basis})
        return pd.DataFrame(rows)

    def save(self, out_dir):
        out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
        json.dump(self.capability_report(), open(out / "BROKER_CAPABILITY.json", "w"), indent=1)
        pd.DataFrame([asdict(s) for s in self.symbols.values()]).to_csv(
            out / "BROKER_SYMBOLS.csv", index=False)
        return out


def _count(items, attr) -> dict:
    out = {}
    for i in items:
        v = getattr(i, attr, "") or "?"
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
