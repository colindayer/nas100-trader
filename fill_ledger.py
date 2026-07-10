"""
fill_ledger.py -- execution fill ledger (logging ONLY).

One CSV row per submitted/finalized order in logs/fills.csv, recorded at the
shared order boundary (broker.place_order_safe). Captures what the research
assumed (signal price) vs what the broker delivered (bid/ask/fill) so the
live-vs-backtest cost gap becomes measurable (see LOSING_TRADE_FORENSICS.md).

Guarantees:
- NEVER affects trading: every public function swallows every exception.
  A ledger failure logs a warning and the order proceeds exactly as before.
- Append-safe: opens in append mode with csv.writer; header written only when
  the file is absent or empty.
- Never fabricates values: anything unavailable is an empty field.
"""
import csv
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("trader")

LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "logs", "fills.csv")

FIELDS = [
    "timestamp_utc", "broker", "account", "strategy", "session", "symbol",
    "side", "quantity", "signal_timestamp", "signal_price",
    "bid_at_submission", "ask_at_submission", "spread", "spread_bps",
    "requested_price", "fill_price", "slippage", "slippage_bps",
    "stop_price", "target_price", "account_equity", "risk_scale",
    "order_id", "position_id", "dry_run", "status", "error",
]

# Session-level context, set once per run by live_trader (session name, equity,
# risk scale). Missing context -> empty fields, never a crash.
CONTEXT = {}


def set_context(**kw):
    try:
        CONTEXT.update({k: v for k, v in kw.items() if v is not None})
    except Exception:
        pass


def _fmt(v, nd=5):
    if v is None or v == "":
        return ""
    try:
        f = float(v)
        return f"{f:.{nd}f}".rstrip("0").rstrip(".") if f == f else ""
    except (TypeError, ValueError):
        return str(v)


def _derive(row):
    """Fill spread/slippage derived fields only when both inputs exist."""
    try:
        bid, ask = row.get("bid_at_submission"), row.get("ask_at_submission")
        if bid not in (None, "") and ask not in (None, ""):
            bid, ask = float(bid), float(ask)
            row["spread"] = ask - bid
            mid = (ask + bid) / 2.0
            if mid:
                row["spread_bps"] = (ask - bid) / mid * 1e4
        sig, fill = row.get("signal_price"), row.get("fill_price")
        if sig not in (None, "") and fill not in (None, ""):
            sig, fill = float(sig), float(fill)
            side = str(row.get("side", "")).lower()
            sgn = 1.0 if side == "buy" else -1.0
            row["slippage"] = sgn * (fill - sig)          # + = paid worse than signal
            if sig:
                row["slippage_bps"] = sgn * (fill - sig) / sig * 1e4
    except Exception:
        pass
    return row


def record(**kw):
    """Append one row. Unknown keys ignored; missing keys -> empty fields.
    Absolutely never raises."""
    try:
        row = {k: "" for k in FIELDS}
        row["timestamp_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        for k in ("session", "account_equity", "risk_scale"):
            if CONTEXT.get(k) is not None:
                row[k] = CONTEXT[k]
        for k, v in kw.items():
            if k in FIELDS and v is not None:
                row[k] = v
        row = _derive(row)
        out = {k: _fmt(row[k]) if k not in ("timestamp_utc", "signal_timestamp")
               else str(row[k]) for k in FIELDS}
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        need_header = (not os.path.exists(LEDGER_PATH)
                       or os.path.getsize(LEDGER_PATH) == 0)
        with open(LEDGER_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if need_header:
                w.writeheader()
            w.writerow(out)
    except Exception as e:
        try:
            logger.warning(f"fill_ledger: record failed ({e}) -- order unaffected")
        except Exception:
            pass
