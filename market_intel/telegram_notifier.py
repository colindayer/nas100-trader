"""telegram_notifier.py -- PHASE 701 alerts. Sends to an existing Telegram bot. Notification ONLY:
this module cannot place, modify, or close a trade. Fails silently-but-logged if unconfigured.
Env: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations
import json, os, ssl, time, urllib.parse, urllib.request

LOG = "registry/telegram_alerts.jsonl"
CLASSES = ["opportunity", "calendar", "guardian_block", "promotion", "shadow_result",
           "demo_fill", "live_fill", "daily_summary", "critical_error"]
MIN_CONFIDENCE = float(os.environ.get("TELEGRAM_MIN_CONFIDENCE", "0.5"))


def _ssl_context():
    """Windows Python does not use the OS certificate store, so chains fail to verify --
    especially behind AV/corporate TLS interception, which presents a self-signed root.
    Prefer `truststore` (the real Windows store), then `certifi`, then the default.

      py -m pip install truststore          # best on Windows
      py -m pip install --upgrade certifi

    Verification is NEVER disabled. An alert path that trusts anything is worse than no alert:
    it would look healthy while being interceptable.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _cfg():
    return os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


def _log(kind, text, sent, err=None):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({"ts": time.time(), "kind": kind, "text": text[:400],
                            "sent": sent, "error": err}) + "\n")


def send(kind: str, text: str) -> dict:
    if kind not in CLASSES:
        return {"sent": False, "error": f"unknown alert class {kind}"}
    tok, chat = _cfg()
    if not tok or not chat:
        _log(kind, text, False, "unconfigured")
        return {"sent": False, "error": "TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set"}
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text,
                                       "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as r:
            ok = json.loads(r.read().decode()).get("ok", False)
        _log(kind, text, ok)
        return {"sent": ok}
    except Exception as e:
        _log(kind, text, False, str(e)[:120])
        return {"sent": False, "error": str(e)[:120]}


# ---- typed helpers (formatting only) ----
def opportunity(o) -> dict:
    conf = getattr(o, "confidence", 0) or 0
    if conf < MIN_CONFIDENCE:
        return {"sent": False, "error": f"below MIN_CONFIDENCE {MIN_CONFIDENCE}"}
    d = "LONG" if getattr(o, "direction", 0) > 0 else "SHORT"
    return send("opportunity",
                f"<b>OPPORTUNITY</b> {o.instrument} {d}\nconfidence {conf:.2f}\n"
                f"{o.economic_reasoning}\nstop {o.stop_suggestion} target {o.target_suggestion}\n"
                f"for: {', '.join(o.evidence_supporting) or '—'}\n"
                f"against: {', '.join(o.evidence_contradicting) or '—'}\n"
                f"<i>status {o.status} — governance decides execution</i>")


def calendar_alert(ev, minutes_out: int | None = None) -> dict:
    when = f"T-{minutes_out}m" if minutes_out is not None else ev.scheduled
    body = (f"<b>{ev.impact.upper()}</b> {ev.currency} {ev.name} ({when})\n"
            f"prev {ev.previous} · forecast {ev.forecast}")
    if ev.released():
        s = ev.surprise()
        body += f"\n<b>ACTUAL {ev.actual}</b> surprise {s:+.4g} ({(ev.surprise_pct() or 0):+.1%})"
    return send("calendar", body)


def guardian_block(symbol, reasons) -> dict:
    return send("guardian_block", f"<b>GUARDIAN BLOCK</b> {symbol}\n{', '.join(map(str, reasons))}")


def promotion_change(sid, old, new, detail=None) -> dict:
    return send("promotion", f"<b>PROMOTION</b> {sid}\n{old} → <b>{new}</b>\n{detail or ''}")


def fill(kind, symbol, side, volume, price, retcode, ops_note="") -> dict:
    assert kind in ("demo_fill", "live_fill")
    return send(kind, f"<b>{kind.replace('_',' ').upper()}</b> {symbol} {side} {volume}@{price}\n"
                      f"retcode {retcode}\n{ops_note}")


def critical(msg) -> dict:
    return send("critical_error", f"🛑 <b>CRITICAL</b>\n{msg}")


def daily_summary(state: dict) -> dict:
    return send("daily_summary", "<b>DAILY SUMMARY</b>\n" +
                "\n".join(f"{k}: {v}" for k, v in state.items()))


def selftest() -> int:
    """Prove the alert path end to end, INDEPENDENT of safety-state.

    The halt drill is not a reliable alerting test: halt() is a no-op when the state is already
    halted, so it emits nothing and looks identical to a broken notifier. This sends directly
    and reports exactly which step failed.
    """
    tok, chat = _cfg()
    print(f"  TELEGRAM_TOKEN   : {'set (' + tok[:8] + '...)' if tok else 'NOT SET'}")
    print(f"  TELEGRAM_CHAT_ID : {chat or 'NOT SET'}")
    if not tok or not chat:
        print("\n  FAIL: credentials missing in THIS process.")
        print("  SetEnvironmentVariable(...,'User') does not affect an already-open shell —")
        print("  open a NEW PowerShell window and retry.")
        return 1
    r = send("critical_error", "<b>ALERTING SELFTEST</b>\nIf you can read this, the alert "
                               "path works. No trading action was taken.")
    ok = bool(r.get("sent"))
    err = str(r.get("error") or "")
    print(f"\n  send() -> sent={ok} {('error: ' + err[:140]) if not ok else ''}")
    if "CERTIFICATE_VERIFY" in err:
        print("\n  TLS chain not verifiable. This VPS presents a self-signed root (AV or")
        print("  corporate interception). Install the Windows-store bridge and retry:")
        print("      py -m pip install truststore")
        print("      py -m pip install --upgrade certifi")
        print("  Verification is never disabled — an alert path that trusts anything is worse")
        print("  than no alert path.")
    print("  Check your phone. No message despite sent=True means the chat id is wrong.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(selftest())
