"""
status.py -- one-command venue health check. Run on the VPS:  python status.py
(add --ping to also send a Telegram test message). Read-only; places no orders.

Prints, per venue:
  MT5 connected + equity, each symbol map resolving with a live price,
  Telegram wiring, the last scheduled-task results (Windows), and recent log tails.
"""
import os, sys, glob, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

def hr(t): print("\n== " + t + " " + "=" * max(0, 52 - len(t)))

# 1. MT5 connection + symbol maps
hr("MT5 / PEPPERSTONE")
try:
    from mt5_broker import MT5Broker
    b = MT5Broker()
    print(f"  connected: equity={b.get_account():.2f}")
    for internal, mapped in b.SYMBOL_MAP.items():
        try:
            df = b.get_bars(internal, "1Hour", 3)
            print(f"  {internal:5} -> {mapped:8} OK   last close={df['Close'].iloc[-1]:.2f}")
        except Exception as e:
            print(f"  {internal:5} -> {mapped:8} FAIL {type(e).__name__}: {e}")
except Exception as e:
    print(f"  MT5 unavailable: {type(e).__name__}: {e}")

# 2. Telegram
hr("TELEGRAM")
try:
    from broker import load_config
    cfg = load_config("alerts")
    tok = cfg.get("telegram_token", "")
    chat = cfg.get("chat_id", "") or cfg.get("telegram_chat_id", "")
    tok_ok = bool(tok and not tok.startswith("YOUR_"))
    print(f"  token set: {tok_ok} | chat_id set: {bool(chat)}")
    if tok_ok and chat and "--ping" in sys.argv:
        import alerts
        alerts.send("status.py test ping -- venues wired")
        print("  test ping sent -> check your phone")
except Exception as e:
    print(f"  telegram check error: {e}")

# 3. Scheduled task results (Windows only)
hr("SCHEDULED TASKS")
if os.name == "nt":
    for tn in ("Nas100Bot-MT5", "Nas100Bot-BTC", "Nas100Bot-Overnight", "nas100-update"):
        try:
            out = subprocess.run(["schtasks", "/query", "/tn", tn, "/v", "/fo", "LIST"],
                                 capture_output=True, text=True)
            picks = [l.strip() for l in out.stdout.splitlines()
                     if any(k in l for k in ("Last Run Time", "Last Result", "Next Run Time"))]
            print(f"  {tn}:")
            for p in picks:
                print(f"      {p}")
            if not picks:
                print("      not found")
        except Exception as e:
            print(f"  {tn}: {e}")
else:
    print("  (Windows-only; run this on the VPS)")

# 4. Recent log tails
hr("RECENT LOGS")
for f in sorted(glob.glob(os.path.join(HERE, "logs", "*.log"))):
    try:
        lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
        last = lines[-1][:100] if lines else "(empty)"
        print(f"  {os.path.basename(f):20} {len(lines):5} lines | last: {last}")
    except Exception as e:
        print(f"  {os.path.basename(f)}: {e}")

print("\nDone. Telegram test: python status.py --ping")
