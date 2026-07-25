# INCIDENT_RESPONSE

Universal first action: **stop new entries** (MT5 Algo Trading off + `safety_state.halt(...)`).
Universal last action: an **audited** `clear_halt('human:<name>', '<root cause>')`.

| incident | detection | immediate action | recovery | escalation |
|--|--|--|--|--|
| **Broker disconnected** | `startup.py` broker line; `healthcheck` broker FAIL; reconcile returns `RECONCILIATION_FAILED` | none needed — reconciliation already blocks trading | restart MT5, re-login, verify DEMO, re-run verification chain | persists >1h → halt and leave halted |
| **Guardian halt** | `startup.py` guardian `BLOCK` | do not override | read the reason code; fix the cause (stale data, bad snapshot, breached limit) | any `INTERNAL_*_STOP` → stop for the day, review the day's trades |
| **Promotion downgrade** | `startup.py` promotion state lower than expected | halt; do not trade | inspect `belief_v2.json` + audit log for the evidence that moved it | downgrade with no new evidence = **suspect state tampering** |
| **Calendar unavailable** | dashboard "none loaded"; `faireconomy.diagnose()` | none — calendar does not gate execution | check TLS (`truststore`), rate-limit (429), cache age | never scrape as a workaround |
| **Telegram failure** | `telegram_alerts.jsonl` shows `sent:false` | none | check token/chat id | **remember no runner emits alerts — silence proves nothing** |
| **Reconciliation failure** | `startup_reconciler` critical finding; state auto-halted | already halted; leave it | classify each finding; resolve manually | orphan or naked position → human classification required |
| **Unexpected position** | `ORPHAN_POSITION` / `FOREIGN_POSITION` | halt; **never assume ownership** | identify by magic + comment + Journal timestamp; decide manually | foreign magic → another EA is running; find and stop it |
| **Missing stop** | `NAKED_POSITION`; reconcile `CRITICAL` | halt immediately | **manually** attach a stop in MT5, or close manually | this is the exact BTC failure mode — treat as severe |
| **Duplicate execution** | two fills for one `intent_id`; `trade_duplicate_ignored` in audit | halt | compare ledger intents to broker deals; close the surplus manually | recurrence → stop the campaign |
| **Persistence corruption** | `STATE_UNREADABLE` / `STATE_CHECKSUM_MISMATCH` / `STATE_SCHEMA_*` | system already halted (fail-closed) | `.bak` recovery is automatic; else rebuild from the audit log | checksum mismatch with no crash = **possible tampering** |

## Manual close checklist (no automatic closing — ever)
For each position, record **before** acting:
`ticket · symbol · type · volume · open price · current SL/TP · magic · comment · open time`
1. Confirm the **account number** matches the intended account.
2. Confirm `magic` — 770001 = legacy `live_trader` (incident); 880001 = portfolio; anything else = foreign.
3. Confirm the intended action (close / hedge / attach stop) and the expected P&L impact.
4. Close via MT5 **Trade tab → ✕ on that exact ticket**. One at a time.
5. Screenshot before and after. Append to `registry/manual_actions.log`.
**If ticket, symbol, account, or intended action cannot all be proven — do not act. Escalate.**

## Account reset checklist (preparation only — do NOT open or trade a new account)
1. Export MT5 history for 61552095: Journal, Experts, Reports → archive off-VPS.
2. Record final balance, equity, open positions, and the latched kill-switch state.
3. Manually close remaining positions per the checklist above.
4. Confirm `deploy.py --scan-executors` = CLEAN on the VPS.
5. Archive `registry/` (ledger, safety state, audit, evidence) — **do not delete**.
6. Record the new account number, server, and starting balance in a fresh contract note.
7. **Stop. Opening and trading a new account requires separate approval.**
