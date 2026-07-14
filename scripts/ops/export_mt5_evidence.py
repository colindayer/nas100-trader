"""export_mt5_evidence.py -- READ-ONLY MT5 evidence exporter (runs on the VPS).

Reads account/positions/orders/deals/symbols + fills.csv + logs + git state and writes
a sanitized daily snapshot into the PRIVATE evidence repo. Never mutates MT5 (no
order_send / close / modify). Never exports secrets. Windows Task Scheduler runs it.

Usage (on the VPS):
    python scripts/ops/export_mt5_evidence.py --out <private_evidence_repo> [--date YYYY-MM-DD]

Read-only guard: the MT5 wrapper below is a thin allowlist that raises on any
mutating call. Verified by test_evidence_bridge.py (no order_send in this file).
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_lib as ev  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# MT5 calls this exporter is ALLOWED to make -- read-only introspection only.
_ALLOWED_MT5 = {"initialize", "shutdown", "account_info", "positions_get",
                "history_orders_get", "history_deals_get", "symbols_get",
                "symbol_info", "last_error", "terminal_info"}
_FORBIDDEN_MT5 = {"order_send", "order_check", "order_calc_margin", "position_close",
                  "order_close", "market_book_add"}


class ReadOnlyMT5:
    """Wraps the mt5 module; raises on any mutating/trading call (Phase 2 guard)."""
    def __init__(self, mt5):
        self._m = mt5

    def __getattr__(self, name):
        if name in _FORBIDDEN_MT5:
            raise PermissionError(f"read-only exporter refuses mutating MT5 call: {name}")
        if name not in _ALLOWED_MT5:
            raise PermissionError(f"read-only exporter: MT5 call not on allowlist: {name}")
        return getattr(self._m, name)


def _git(*a):
    try:
        return subprocess.run(["git", *a], cwd=REPO, capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _connect():
    """Connect to MT5 read-only using the SAME config the trader uses (no creds exported)."""
    import MetaTrader5 as mt5
    sys.path.insert(0, REPO)
    from broker import load_config
    cfg = load_config("mt5")
    login, pw, server = cfg.get("login", ""), cfg.get("password", ""), cfg.get("server", "")
    if not login or login.startswith("YOUR_"):
        raise SystemExit("MT5 credentials not configured")
    if not mt5.initialize(login=int(login), password=pw, server=server):
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    return ReadOnlyMT5(mt5), str(login), server


def _rows_from(objs, fields):
    out = []
    for o in objs or []:
        out.append({f: getattr(o, f, "") for f in fields})
    return out


def _write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def export(out_root, date_str=None, _mt5conn=None):
    """Write the daily snapshot. _mt5conn lets tests inject a fake (login, server, ro)."""
    today = date_str or _dt.datetime.utcnow().strftime("%Y-%m-%d")
    outdir = os.path.join(out_root, "daily", today)
    os.makedirs(outdir, exist_ok=True)
    manifest = {"generated_at_utc": _dt.datetime.utcnow().isoformat(timespec="seconds"),
                "vps_hostname": socket.gethostname(), "exporter_version": ev.EXPORTER_VERSION,
                "source_commit": _git("rev-parse", "--short", "HEAD"),
                "date": today, "row_counts": {}, "checksums": {}, "status": "partial"}
    counts = manifest["row_counts"]

    if _mt5conn is not None:
        ro, login, server = _mt5conn
    else:
        ro, login, server = _connect()
    manifest["account_masked"] = ev.mask_account(login)   # never the raw login

    try:
        # account.json (masked; NO login/password/server secrets)
        ai = ro.account_info()
        acct = {"account_masked": manifest["account_masked"],
                "currency": getattr(ai, "currency", ""), "leverage": getattr(ai, "leverage", ""),
                "equity": getattr(ai, "equity", ""), "balance": getattr(ai, "balance", ""),
                "margin_free": getattr(ai, "margin_free", "")}
        open(os.path.join(outdir, "account.json"), "w").write(json.dumps(acct, indent=1))

        pos_f = ["ticket", "time", "symbol", "type", "volume", "price_open", "sl", "tp",
                 "price_current", "swap", "profit", "comment"]
        counts["positions"] = _write_csv(os.path.join(outdir, "positions.csv"),
                                         _rows_from(ro.positions_get(), pos_f), pos_f)
        # historical orders + deals for a wide window (read-only)
        frm = _dt.datetime.utcnow() - _dt.timedelta(days=400)
        to = _dt.datetime.utcnow() + _dt.timedelta(days=1)
        ord_f = ["ticket", "time_setup", "symbol", "type", "volume_initial", "price_open",
                 "sl", "tp", "state", "comment"]
        counts["orders"] = _write_csv(os.path.join(outdir, "orders.csv"),
                                      _rows_from(ro.history_orders_get(frm, to), ord_f), ord_f)
        deal_f = ["ticket", "order", "time", "symbol", "type", "entry", "volume", "price",
                  "commission", "swap", "fee", "profit", "comment"]
        counts["deals"] = _write_csv(os.path.join(outdir, "deals.csv"),
                                     _rows_from(ro.history_deals_get(frm, to), deal_f), deal_f)
        manifest["status"] = "ok"
    except Exception as e:
        manifest["status"] = f"mt5_error: {e}"
    finally:
        try:
            ro.shutdown()
        except Exception:
            pass

    # fills.csv (copy the strategy ledger verbatim -- it holds no secrets)
    src_fills = os.path.join(REPO, "logs", "fills.csv")
    if os.path.exists(src_fills):
        data = open(src_fills, encoding="utf-8", errors="replace").read()
        ev.assert_clean(data, "fills.csv")
        open(os.path.join(outdir, "fills.csv"), "w", encoding="utf-8").write(data)
        counts["fills"] = max(0, data.count("\n") - 1)

    # execution_events.csv -- alert/fill/crash lines from trader.log (sanitized)
    ev_rows = []
    tl = os.path.join(REPO, "logs", "trader.log")
    if os.path.exists(tl):
        for line in open(tl, encoding="utf-8", errors="replace").read().splitlines()[-2000:]:
            if any(k in line for k in ("FILL", "CRASH", "KILL", "ORDER", "SIGNAL")) and not ev.scan_secrets(line):
                ev_rows.append({"line": line[:300]})
    counts["execution_events"] = _write_csv(os.path.join(outdir, "execution_events.csv"),
                                            ev_rows, ["line"])

    # scheduler.json (best-effort; empty off-Windows)
    sched = {}
    try:
        r = subprocess.run(["schtasks", "/query", "/tn", "nas100-evidence-export", "/fo", "LIST", "/v"],
                           capture_output=True, text=True, timeout=15)
        sched = {"raw": r.stdout[-2000:]} if r.returncode == 0 else {"note": "task not found or non-Windows"}
    except Exception:
        sched = {"note": "schtasks unavailable"}
    open(os.path.join(outdir, "scheduler.json"), "w").write(json.dumps(sched, indent=1))

    # git_state.json
    open(os.path.join(outdir, "git_state.json"), "w").write(json.dumps(
        {"commit": _git("rev-parse", "HEAD"), "short": _git("rev-parse", "--short", "HEAD"),
         "branch": _git("branch", "--show-current"),
         "dirty": bool(_git("status", "--porcelain"))}, indent=1))

    # data_quality.json
    dq = {"has_positions": counts.get("positions", 0) > 0,
          "has_deals": counts.get("deals", 0) > 0,
          "has_fills": counts.get("fills", 0) > 0,
          "mt5_status": manifest["status"]}
    open(os.path.join(outdir, "data_quality.json"), "w").write(json.dumps(dq, indent=1))

    # checksums for every file (except the manifest itself)
    for fn in sorted(os.listdir(outdir)):
        if fn != "manifest.json":
            fp = os.path.join(outdir, fn)
            # final secret sweep on text files
            if fn.endswith((".csv", ".json")):
                ev.assert_clean(open(fp, encoding="utf-8", errors="replace").read(), fn)
            manifest["checksums"][fn] = ev.sha256_file(fp)
    manifest["success"] = manifest["status"] == "ok"
    open(os.path.join(outdir, "manifest.json"), "w").write(json.dumps(manifest, indent=1))
    return outdir, manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="private evidence repo root")
    ap.add_argument("--date", default=None)
    args = ap.parse_args()
    outdir, m = export(args.out, args.date)
    print(f"exported {outdir} status={m['status']} counts={m['row_counts']}")
    sys.exit(0 if m.get("success") or m["row_counts"].get("fills") else 2)


if __name__ == "__main__":
    main()
