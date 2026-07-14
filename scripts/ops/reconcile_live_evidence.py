"""reconcile_live_evidence.py -- reconcile a daily evidence snapshot (Mac side).

Joins fills.csv -> MT5 orders -> deals -> open positions and measures execution.
Unknown values stay UNKNOWN (never estimated). Emits reports/<date>_LIVE_EVIDENCE.md
+ reports/latest.json + a stable reports/latest pointer. Read-only; no MT5, no trading.

Usage: python scripts/ops/reconcile_live_evidence.py --snapshot <evidence>/daily/YYYY-MM-DD
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime

MIN_SAMPLE = 10   # below this: no expectancy verdict (INSUFFICIENT_SAMPLE)


def rows(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def _f(v):
    try:
        return float(str(v).replace(" ", ""))
    except (TypeError, ValueError):
        return None


def reconcile(snap):
    fills = [r for r in rows(os.path.join(snap, "fills.csv"))
             if str(r.get("dry_run", "")).lower() != "true"]
    deals = rows(os.path.join(snap, "deals.csv"))
    positions = rows(os.path.join(snap, "positions.csv"))
    recs, anomalies = [], []

    def find_deals(f):
        oid, pid = str(f.get("order_id", "")), str(f.get("position_id", ""))
        return [d for d in deals if str(d.get("order")) == oid or str(d.get("ticket")) == pid]

    def find_pos(f):
        oid, pid = str(f.get("order_id", "")), str(f.get("position_id", ""))
        return [p for p in positions if str(p.get("ticket")) in (oid, pid)]

    for f in fills:
        md = find_deals(f)
        mp = find_pos(f)
        # in-deal (entry)
        entry_deal = next((d for d in md if str(d.get("entry")) in ("0", "in", "DEAL_ENTRY_IN")), md[0] if md else None)
        out_deal = next((d for d in md if str(d.get("entry")) in ("1", "out", "DEAL_ENTRY_OUT")), None)
        rec = {"strategy": f.get("strategy"), "symbol_ledger": f.get("symbol"),
               "order_id": f.get("order_id"), "position_id": f.get("position_id"),
               "ledger_fill": _f(f.get("fill_price")), "spread_bps": _f(f.get("spread_bps")),
               "slippage_bps": _f(f.get("slippage_bps")), "risk_scale": _f(f.get("risk_scale")),
               "matched_deal": bool(entry_deal), "matched_position": bool(mp)}
        if entry_deal:
            rec["broker_symbol"] = entry_deal.get("symbol")
            rec["broker_fill"] = _f(entry_deal.get("price"))
            # swap/commission accrue across in+out legs (+ open position) -- sum them
            swaps = [_f(dd.get("swap")) for dd in md if _f(dd.get("swap")) is not None]
            if mp and _f(mp[0].get("swap")) is not None:
                swaps.append(_f(mp[0].get("swap")))
            rec["swap"] = round(sum(swaps), 2) if swaps else None
            comms = [_f(dd.get("commission")) for dd in md if _f(dd.get("commission")) is not None]
            rec["commission"] = round(sum(comms), 2) if comms else None
            # price-match ledger vs broker
            if rec["ledger_fill"] and rec["broker_fill"] and abs(rec["ledger_fill"] - rec["broker_fill"]) > 0.5:
                anomalies.append(f"{f.get('order_id')}: ledger fill {rec['ledger_fill']} != broker {rec['broker_fill']}")
        else:
            anomalies.append(f"MISSING FILL: ledger order {f.get('order_id')} has no broker deal")
        # realized vs open
        if out_deal:
            rec["state"] = "CLOSED"; rec["realized_profit"] = _f(out_deal.get("profit"))
            entry_p, stop = rec.get("broker_fill"), _f(f.get("stop_price"))
            exit_p = _f(out_deal.get("price"))
            rec["realized_R"] = round((exit_p - entry_p) / (entry_p - stop), 2) if (exit_p and entry_p and stop and entry_p != stop) else "UNKNOWN"
        elif mp:
            rec["state"] = "OPEN"; rec["unrealized_profit"] = _f(mp[0].get("profit"))
            rec["realized_R"] = "UNKNOWN (open)"
        else:
            rec["state"] = "UNKNOWN"; rec["realized_R"] = "UNKNOWN"
        # 4-stage latency: signal_bar -> decision -> submission -> fill. Prefer the
        # TRUE broker deal time for fill; UNKNOWN whenever a stamp is blank (never est.)
        def _dt(v):
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
        sb, dc, sub = _dt(f.get("signal_bar_timestamp")), _dt(f.get("decision_timestamp")), _dt(f.get("submission_timestamp"))
        broker_fill_t = _dt(entry_deal.get("time")) if entry_deal else None
        fil = broker_fill_t or _dt(f.get("fill_timestamp"))

        def _lat(a, b):
            if a and b:
                try:
                    return round((b - a).total_seconds(), 1)
                except Exception:
                    return "UNKNOWN"
            return "UNKNOWN"
        rec["latency_staleness_s"] = _lat(sb, dc)      # bar close -> decision
        rec["latency_processing_s"] = _lat(dc, sub)    # decision -> submission
        rec["latency_broker_s"] = _lat(sub, fil)       # submission -> fill
        rec["signal_to_submit_latency"] = "UNKNOWN" if not f.get("decision_timestamp") else _lat(dc, sub)
        # duplicate detection
        if len([d for d in md if str(d.get("entry")) in ("0", "in", "DEAL_ENTRY_IN")]) > 1:
            anomalies.append(f"DUPLICATE FILL: order {f.get('order_id')} has >1 entry deal")
        recs.append(rec)

    matched = sum(1 for r in recs if r["matched_deal"])
    status = ("EXPORT_FAILED" if not fills and not deals else
              "EXECUTION_ANOMALY" if anomalies else
              "INSUFFICIENT_SAMPLE" if len(fills) < MIN_SAMPLE else "HEALTHY")
    slips = [r["slippage_bps"] for r in recs if r.get("slippage_bps") is not None]
    sprs = [r["spread_bps"] for r in recs if r.get("spread_bps") is not None]
    swaps = [r["swap"] for r in recs if r.get("swap") is not None]
    return {"status": status, "n_fills": len(fills), "n_deals": len(deals),
            "matched": matched, "match_rate": round(matched / max(len(fills), 1), 3),
            "anomalies": anomalies, "records": recs,
            "avg_slippage_bps": round(sum(slips) / len(slips), 3) if slips else "UNKNOWN",
            "avg_spread_bps": round(sum(sprs) / len(sprs), 3) if sprs else "UNKNOWN",
            "total_swap": round(sum(swaps), 2) if swaps else "UNKNOWN"}


def write_reports(repo, snap, result):
    date = os.path.basename(snap.rstrip("/"))
    rdir = os.path.join(repo, "reports")
    os.makedirs(rdir, exist_ok=True)
    md = [f"# LIVE EVIDENCE — {date}", f"\n**Status: {result['status']}** · fills {result['n_fills']} · "
          f"deals {result['n_deals']} · match rate {result['match_rate']:.0%}",
          f"\navg slippage {result['avg_slippage_bps']} bps · avg spread {result['avg_spread_bps']} bps · "
          f"total swap {result['total_swap']}"]
    if result["n_fills"] < MIN_SAMPLE:
        md.append(f"\n> SAMPLE-SIZE WARNING: n={result['n_fills']} < {MIN_SAMPLE}. "
                  f"No strategy-profitability conclusion is drawn.")
    md.append("\n## Per-fill reconciliation")
    md.append("| strategy | order | broker sym | ledger→broker fill | slip bps | swap | state | R |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in result["records"]:
        md.append(f"| {r['strategy']} | {r['order_id']} | {r.get('broker_symbol','—')} | "
                  f"{r['ledger_fill']}→{r.get('broker_fill','MISSING')} | {r.get('slippage_bps','—')} | "
                  f"{r.get('swap','—')} | {r['state']} | {r['realized_R']} |")
    if result["anomalies"]:
        md.append("\n## Anomalies\n" + "\n".join(f"- {a}" for a in result["anomalies"]))
    else:
        md.append("\n## Anomalies\n- none")
    open(os.path.join(rdir, f"{date}_LIVE_EVIDENCE.md"), "w").write("\n".join(md) + "\n")
    latest = {"date": date, "generated_utc": datetime.utcnow().isoformat(timespec="seconds"), **result}
    open(os.path.join(rdir, "latest.json"), "w").write(json.dumps(latest, indent=1, default=str))
    open(os.path.join(rdir, "latest"), "w").write(f"{date}_LIVE_EVIDENCE.md\n")  # stable pointer
    return os.path.join(rdir, f"{date}_LIVE_EVIDENCE.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--repo", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    args = ap.parse_args()
    result = reconcile(args.snapshot)
    path = write_reports(args.repo, args.snapshot, result)
    print(f"{result['status']} | fills {result['n_fills']} matched {result['matched']} | {path}")
    sys.exit(0 if result["status"] in ("HEALTHY", "INSUFFICIENT_SAMPLE") else 2)


if __name__ == "__main__":
    import sys
    main()
