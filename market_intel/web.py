"""web.py -- PHASE 701 web interface. Read-only HTML view of market intelligence, calendar,
opportunities, belief + guardian status. Serves on localhost. Places no orders (no broker imports).
Run:  py -m market_intel.web --port 8787 --symbols EURUSD,XAUUSD,NAS100
"""
from __future__ import annotations
import argparse, html, json, os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from . import calendar_feed as cal
from .opportunity import OpportunityRegistry

SYMBOLS = ["EURUSD", "XAUUSD", "NAS100"]
CSS = """body{font:14px -apple-system,Segoe UI,sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:24px}
h1{font-size:18px;margin:0 0 4px}h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#8b949e;margin:26px 0 8px}
table{border-collapse:collapse;width:100%;margin-bottom:8px}th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #21262d}
th{color:#8b949e;font-weight:600;font-size:12px}.up{color:#3fb950}.down{color:#f85149}.warn{color:#d29922}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;background:#21262d}
.shadow{background:#1f2937;color:#d29922;border:1px solid #d29922}.card{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;margin-bottom:10px}
small{color:#6e7681}"""


def _state_rows(symbols):
    rows = []
    try:
        import MetaTrader5 as mt5, pandas as pd
        from .state import classify
        if mt5.initialize():
            for s in symbols:
                try:
                    def g(tf, n):
                        r = mt5.copy_rates_from_pos(s, tf, 0, n)
                        if r is None or not len(r): return None
                        d = pd.DataFrame(r); d["time"] = pd.to_datetime(d["time"], unit="s", utc=True)
                        return d.set_index("time")[["open", "high", "low", "close"]]
                    m5, d1 = g(mt5.TIMEFRAME_M5, 600), g(mt5.TIMEFRAME_D1, 90)
                    if m5 is None or d1 is None: continue
                    rows.append(classify(s, m5, d1))
                except Exception:
                    continue
    except Exception:
        pass
    return rows


def page(symbols):
    now = datetime.now(timezone.utc)
    states = _state_rows(symbols)
    events = cal.load()
    up = cal.upcoming(events, now=now, hours=48)
    opps = OpportunityRegistry().all()
    try:
        from execution_safety.belief_reader import decide
        bdec, bdet = decide("H_portfolio_multisleeve")
    except Exception as e:
        bdec, bdet = "UNKNOWN", {"error": str(e)[:80]}

    h = [f"<style>{CSS}</style><h1>Market Intelligence</h1>",
         f"<small>{now:%Y-%m-%d %H:%M UTC}</small> &nbsp;",
         "<span class='badge shadow'>EXECUTION: SHADOW — no orders</span>"]

    h.append("<h2>Market state</h2><table><tr><th>symbol</th><th>price</th><th>trend</th><th>vol</th>"
             "<th>session</th><th>kill zone</th><th>structure</th><th>sweep</th><th>fvg</th>"
             "<th>PDH / PDL</th><th>VWAP dist</th></tr>")
    for s in states:
        cls = "up" if s.trend == "up" else "down" if s.trend == "down" else ""
        h.append(f"<tr><td><b>{html.escape(s.symbol)}</b></td><td>{s.price:.5f}</td>"
                 f"<td class='{cls}'>{s.trend}</td><td>{s.volatility_regime}</td><td>{s.session}</td>"
                 f"<td>{','.join(s.kill_zones) or '—'}</td><td>{s.structure}</td>"
                 f"<td>{s.liquidity_sweep}</td><td>{s.fvg}</td>"
                 f"<td>{s.prev_day_high:.5f} / {s.prev_day_low:.5f}</td>"
                 f"<td>{s.dist_vwap_pct:+.3%}</td></tr>")
    if not states:
        h.append("<tr><td colspan=11>no MT5 data (terminal running?)</td></tr>")
    h.append("</table>")

    # ---------- MACRO BOARD (evidence-linked; no direction, no signal) ----------
    try:
        from .macro_board import board as _macro
        mb = _macro()
        h.append("<h2>Macro board</h2>")
        h.append("<table><tr><th>dimension</th><th>claim</th><th>evidence</th>"
                 "<th>contradictions</th><th>unknowns</th><th>coverage</th></tr>")
        for dim, c in mb["claims"].items():
            ev = "; ".join(f"{a} {b}" for a, b, _ in c["evidence"][:4]) or "—"
            src = ", ".join(sorted({s for _, _, s in c["evidence"] if s}))[:60]
            contra = "; ".join(c["contradictions"]) or "—"
            unk = "; ".join(c["unknowns"][:2]) or "—"
            cls = ("warn" if "UNKNOWN" in c["statement"] else
                   "up" if ("risk-on" in c["statement"] or "rising" in c["statement"]) else
                   "down" if ("risk-off" in c["statement"] or "falling" in c["statement"]) else "")
            h.append(f"<tr><td><b>{html.escape(dim)}</b></td>"
                     f"<td class='{cls}'>{html.escape(c['statement'])}</td>"
                     f"<td><small>{html.escape(ev)}<br><i>{html.escape(src)}</i></small></td>"
                     f"<td><small class='down'>{html.escape(contra)}</small></td>"
                     f"<td><small>{html.escape(unk)}</small></td>"
                     f"<td>{c['confidence']:.2f}</td></tr>")
        h.append("</table>")
        h.append("<div class='card'><small>Evidence only — no direction, no signal. "
                 "<b>'coverage' is how much evidence was available, NOT a probability of profit.</b> "
                 "Contradictions are shown, never resolved; unknowns are listed, never hidden.</small></div>")

        if mb["latest_releases"]:
            h.append("<h2>Latest releases — measured surprise</h2><table>"
                     "<tr><th>ccy</th><th>event</th><th>forecast</th><th>actual</th>"
                     "<th>surprise</th><th>source</th></tr>")
            for r in mb["latest_releases"]:
                sp = r["surprise"]; spc = r.get("surprise_pct")
                cls = "up" if sp and sp > 0 else "down" if sp and sp < 0 else ""
                h.append(f"<tr><td>{html.escape(str(r['currency']))}</td>"
                         f"<td>{html.escape(str(r['name']))}</td><td>{r['forecast']}</td>"
                         f"<td><b>{r['actual']}</b></td>"
                         f"<td class='{cls}'>{sp:+.4g}"
                         f"{f' ({spc:+.1%})' if spc is not None else ''}</td>"
                         f"<td><small>{html.escape(str(r['provider']))}</small></td></tr>")
            h.append("</table>")
    except Exception as e:
        h.append(f"<div class='card'>macro board unavailable: {html.escape(str(e)[:120])}</div>")

    h.append("<h2>Economic calendar — next 48h</h2><table>"
             "<tr><th>countdown</th><th>impact</th><th>ccy</th><th>event</th>"
             "<th>prev</th><th>forecast</th><th>actual</th><th>surprise</th></tr>")
    for e in up[:15]:
        try:
            t = datetime.fromisoformat(e.scheduled.replace("Z", "+00:00"))
            m = int((t - now).total_seconds() // 60); cd = f"T-{m//60}h{m%60:02d}m" if m > 0 else "DUE"
        except Exception:
            cd = "?"
        sp = e.surprise()
        h.append(f"<tr><td>{cd}</td><td class='{'warn' if e.impact=='high' else ''}'>{e.impact}</td>"
                 f"<td>{html.escape(e.currency)}</td><td>{html.escape(e.name)}</td>"
                 f"<td>{e.previous}</td><td>{e.forecast}</td><td>{e.actual if e.actual is not None else '—'}</td>"
                 f"<td>{f'{sp:+.4g}' if sp is not None else '—'}</td></tr>")
    if not up:
        h.append("<tr><td colspan=8>no calendar feed — set CALENDAR_API_URL / CALENDAR_API_TOKEN"
                 " or drop market_intel/calendar.csv</td></tr>")
    h.append("</table>")

    h.append("<h2>Opportunities</h2>")
    if not opps:
        h.append("<div class='card'><small>none yet — generated only AFTER an official Actual is published</small></div>")
    for o in opps[-10:][::-1]:
        h.append(f"<div class='card'><b>{html.escape(o['instrument'])}</b> "
                 f"dir {o['direction']:+d} · conf {o['confidence']} · "
                 f"<span class='badge'>{html.escape(o['status'])}</span><br>"
                 f"<small>{html.escape(o['economic_reasoning'])}</small><br>"
                 f"<small>for: {html.escape(', '.join(o['evidence_supporting']))} | "
                 f"against: {html.escape(', '.join(o['evidence_contradicting']) or 'none')}</small></div>")

    # ---- PHASE 702.1: separate Research vs Operational belief + promotion state ----
    try:
        from execution_safety.promotion_pipeline_v2 import evaluate, REQUIREMENTS, STATES
        st = evaluate("portfolio_multisleeve")
        rb, ob = st["research_belief"], st["operational_belief"]
        def bar(v, tgt):
            pct = int(min(1.0, v) * 100); col = "#3fb950" if v >= tgt else "#d29922"
            return (f"<div style='background:#21262d;border-radius:4px;height:8px;width:220px;display:inline-block;"
                    f"vertical-align:middle'><div style='background:{col};height:8px;width:{pct*2.2:.0f}px;"
                    f"border-radius:4px'></div></div>")
        h.append("<h2>Belief &amp; promotion</h2><div class='card'>")
        h.append(f"<b>STATE: {html.escape(st['state'])}</b> &nbsp;"
                 f"<small>next: {html.escape(str(st['next_state']))}</small><br><br>")
        h.append(f"Research belief &nbsp;<b>{rb:.4f}</b> {bar(rb,0.60)} <small>live bar 0.60</small><br>")
        h.append(f"Operational belief <b>{ob:.4f}</b> {bar(ob,0.85)} <small>live bar 0.85</small><br><br>")
        h.append(f"demo trades: <b>{st['demo_trades']}</b> &nbsp; position cap: {st['position_cap']} "
                 f"&nbsp; risk/trade: {st['risk_cap_pct']:.2%}<br>")
        if st["outstanding_defects"]:
            h.append(f"<br><span class='down'>outstanding defects ({len(st['outstanding_defects'])}):</span> "
                     f"<small>{html.escape('; '.join(st['outstanding_defects'][:4]))}</small>")
        h.append("</div>")
        # remaining requirements for the next two gates
        h.append("<div class='card'><b>Remaining requirements</b><table>"
                 "<tr><th>gate</th><th>research</th><th>operational</th><th>demo trades</th><th>status</th></tr>")
        for gate in ("FULL_DEMO_APPROVED", "LIVE_APPROVED"):
            r = REQUIREMENTS[gate]
            met = STATES.index(st["state"]) >= STATES.index(gate)
            need = st["blocking"].get(gate, [])
            h.append(f"<tr><td>{gate}</td>"
                     f"<td class=\"{'up' if rb>=r['research_min'] else 'warn'}\">{rb:.3f} / {r['research_min']}</td>"
                     f"<td class=\"{'up' if ob>=r['ops_min'] else 'warn'}\">{ob:.3f} / {r['ops_min']}</td>"
                     f"<td>{st['demo_trades']} / {r['min_demo_trades']}</td>"
                     f"<td>{'MET' if met else html.escape('; '.join(need) or 'pending')}</td></tr>")
        h.append("</table></div>")
        # evidence statistics
        from execution_safety.belief_graph_v2 import BeliefGraphV2, EVIDENCE_CLASSES
        sb = BeliefGraphV2().get("portfolio_multisleeve")
        counts = {c: sb.count(c) for c in EVIDENCE_CLASSES}
        h.append("<div class='card'><b>Evidence</b><br>" +
                 " &nbsp; ".join(f"{k}: <b>{v}</b>" for k, v in counts.items() if v) +
                 (f"<br><small>total {len(sb.evidence)} items</small>" if sb.evidence else
                  "<small>no evidence recorded</small>") + "</div>")
    except Exception as e:
        h.append(f"<div class='card'>belief/promotion unavailable: {html.escape(str(e)[:120])}</div>")

    tg_tok = bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
    h.append("<h2>Pipeline status</h2><div class='card'>"
             f"Legacy belief reader: <b>{bdec}</b> <small>{html.escape(json.dumps(bdet))}</small><br>"
             "Guardian: evaluated at order time (fail-closed)<br>"
             f"Telegram: <b>{'configured' if tg_tok else 'not configured'}</b><br>"
             "Execution: <b class='warn'>SHADOW</b> — this interface can never place a trade"
             "</div>")
    return "".join(h)


class H(BaseHTTPRequestHandler):
    symbols = SYMBOLS
    token = None                      # when bound off-localhost a token is REQUIRED

    def do_GET(self):
        if self.token:
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            if q.get("t", [None])[0] != self.token:
                msg = b"401 - append ?t=YOUR_TOKEN to the URL"
                self.send_response(401); self.send_header("Content-Length", str(len(msg)))
                self.end_headers(); self.wfile.write(msg); return
        body = ("<meta http-equiv='refresh' content='30'>" + page(self.symbols)).encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a): pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 exposes it on the network (a token is then REQUIRED)")
    ap.add_argument("--token", default=None, help="shared secret; auto-generated if --host is public")
    a = ap.parse_args()
    H.symbols = [s.strip() for s in a.symbols.split(",") if s.strip()]
    public = a.host not in ("127.0.0.1", "localhost")
    if public:
        import secrets
        H.token = a.token or secrets.token_urlsafe(16)
        print("=" * 66)
        print("  PUBLIC BIND - this page is reachable from the network.")
        print(f"  TOKEN: {H.token}")
        # resolve the real outward-facing IP instead of printing a placeholder
        import socket
        lan = "?"
        try:
            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _s.connect(("8.8.8.8", 80)); lan = _s.getsockname()[0]; _s.close()
        except Exception:
            pass
        pub = None
        try:
            import urllib.request
            pub = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode().strip()
        except Exception:
            pass
        print(f"  LOCAL: http://localhost:{a.port}/?t={H.token}")
        print(f"  LAN:   http://{lan}:{a.port}/?t={H.token}")
        if pub:
            print(f"  PUBLIC:http://{pub}:{a.port}/?t={H.token}   <- open this from your Mac")
        print(f"  Firewall: New-NetFirewallRule -DisplayName 'MarketIntel {a.port}' "
              f"-Direction Inbound -LocalPort {a.port} -Protocol TCP -Action Allow")
        print("  Open the port in Windows Firewall, and prefer restricting it to your own IP.")
        print("  The page is READ-ONLY and cannot place trades, but it does reveal account state.")
        print("=" * 66)
    else:
        print(f"Market Intelligence -> http://localhost:{a.port}  (refreshes 30s, SHADOW only)")
    HTTPServer((a.host, a.port), H).serve_forever()
