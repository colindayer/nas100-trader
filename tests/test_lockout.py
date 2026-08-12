"""A rejected order must NOT cost the bot its whole day."""
import sys, types, pathlib, tempfile, json
sys.path.insert(0, ".")
import pandas as pd
import challenge_controller as C

def build(rows):
    """Replicates main()'s traded_today logic exactly."""
    today = pd.Timestamp.now(tz="Europe/London").date().isoformat()
    traded, att = {}, {}
    for t in rows:
        if t.get("kind") == "close" or not t.get("timestamp","").startswith(today):
            continue
        sid = t["strategy_id"]; att[sid] = att.get(sid,0)+1
        if t.get("ticket"): traded[sid] = True
    for sid,n in att.items():
        if n >= C.MAX_ORDER_ATTEMPTS_PER_DAY and sid not in traded: traded[sid]=True
    return traded

ts = pd.Timestamp.now(tz="Europe/London").isoformat()
A = "BOT_A"
assert build([{"strategy_id":A,"timestamp":ts,"retcode":10016,"ticket":None}]) == {}, \
    "one rejection locked the bot out"
assert build([{"strategy_id":A,"timestamp":ts,"ticket":None}]*2) == {}, "two rejections locked out"
assert build([{"strategy_id":A,"timestamp":ts,"ticket":None}]*3) == {A:True}, "no rejection cap"
assert build([{"strategy_id":A,"timestamp":ts,"ticket":777}]) == {A:True}, "a fill must close the session"
# a close record must never count as a new attempt
assert build([{"strategy_id":A,"timestamp":ts,"ticket":777},
              {"kind":"close","strategy_id":A,"timestamp":ts}]) == {A:True}
# yesterday must not bleed into today
assert build([{"strategy_id":A,"timestamp":"2020-01-01T06:30","ticket":777}]) == {}
print("LOCKOUT CHECKS PASS: rejection retries up to 3, fill ends the session")
