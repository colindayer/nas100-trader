"""Equity baselines must belong to ONE account. Halts must survive an account change.

Regression for 2026-08-02: safety_state.json carried day_start_equity 49,338.76 from Pepperstone
61552095 while the runner was connected to FundedNext 34536803 at equity 50,000. Drawdown limits
were therefore computed against a different broker's account. The state file had no account
field at all.

    python tests/test_account_binding.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from execution_safety import safety_state as ss

PEPPERSTONE, FUNDEDNEXT = 61552095, 34536803


def main():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "safety_state.json")

    # ---- account A establishes baselines
    st, _ = ss.load(p, equity=50_000.0, login=PEPPERSTONE)
    assert st.account_login == PEPPERSTONE
    st, _ = ss.load(p, equity=49_338.76, login=PEPPERSTONE)
    assert st.high_water_mark == 50_000.0, "HWM must not fall on a loss"
    assert st.day_start_equity == 50_000.0

    # ---- account B must NOT inherit A's baselines
    st, notes = ss.load(p, equity=50_000.0, login=FUNDEDNEXT)
    assert st.account_login == FUNDEDNEXT
    assert st.day_start_equity == 50_000.0, "baseline must be rebased to the new account"
    assert st.high_water_mark == 50_000.0, "HWM must be rebased, not inherited"
    assert any("ACCOUNT CHANGED" in n for n in notes), f"the switch must be announced: {notes}"

    # ---- a halt is NOT per-account: it is sticky across a switch
    ss.halt("test halt", path=p)
    st, notes = ss.load(p, equity=50_000.0, login=PEPPERSTONE)
    assert st.halted, "a halt must survive an account change — it describes the SYSTEM"
    assert st.account_login == PEPPERSTONE

    # ---- trades_today is per-account and resets on the switch
    ss.clear_halt("test", path=p)
    ss.record_trade("i1", path=p, max_per_day=3)
    st, _ = ss.load(p, login=PEPPERSTONE)
    assert st.trades_today == 1
    st, _ = ss.load(p, equity=50_000.0, login=FUNDEDNEXT)
    assert st.trades_today == 0, "another account's trade count must not consume our daily cap"

    # ---- omitting login must not silently rebase anything
    before = (st.day_start_equity, st.high_water_mark, st.account_login)
    st2, _ = ss.load(p, equity=12_345.0)
    assert (st2.day_start_equity, st2.account_login) == (before[0], before[2]), \
        "a call without login must not reassign the account"

    print("PASS — baselines are per-account, halts are system-wide, daily caps do not leak")


if __name__ == "__main__":
    main()
