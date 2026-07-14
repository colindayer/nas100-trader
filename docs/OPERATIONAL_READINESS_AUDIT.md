# OPERATIONAL READINESS AUDIT — can a validated trade become a successful live trade?

_2026-07-14. Strategy quality IGNORED (frozen). Audit-only; NO code changed. Scope:
scheduling, logging, MT5, broker responses, dashboards, alerts, Trade Explorer, VPS
automation, backups, recovery, monitoring, evidence, docs. Ranked by probability ×
impact. Evidence cited by file:line. Deliverable = the prioritized checklist below._

## Ranked issues (probability × impact)

| # | issue | evidence | P | I | P×I | class |
|---|---|---|---|---|---|---|
| 1 | **Daily kill-switch effectively DISABLED.** `daily_start_equity` defaults to `session_start_equity` which the template sets to `0` → `daily_pnl_pct` is never negative → the 5% daily halt never fires. Nothing sets true session-start equity per run. | live_trader.py:1072-1074; config.example.ini:52 | HIGH | CRITICAL | **9** | do first |
| 2 | **MT5 has no mid-session reconnect.** `initialize()` runs once at construction; a transient terminal drop makes `account_info()` return None → `get_account` RAISES → uncaught → whole session crashes (misses all trades that run). | mt5_broker.py:64-66,123-127 | HIGH | HIGH | **9** | do first |
| 3 | **Alert delivery is unmonitored / fails silently.** `alerts.send` swallows every exception and returns. A dead bot, bad token, or network blip means CRASH/FILL/kill alerts silently never arrive — no dead-man's switch. | alerts.py:53,74 | MED-HIGH | HIGH | **8** | do first |
| 4 | **Single-VPS SPOF, no heartbeat-of-heartbeat.** One Windows VPS; if it's down mid-session, trades are missed and the only signal is a human running `status.py`. No external "did the bot run?" watchdog. | CURRENT_PROJECT_STATE blocker #7 | HIGH | HIGH | **8** | do first |
| 5 | **Secrets never rotated** (pasted in chats). Not an availability issue but a live-money blast radius. | PROP_READINESS blocker | MED | CRITICAL | **7** | before real money |
| 6 | **No backups of `state/`.** `risk_state_<broker>.json` holds the DD-throttle PEAK-equity baseline; if the VPS/disk dies or the file corrupts, throttle resets → silent OVERSIZING on rebuild. Also ovn/btc-trend state. | logs/risk_state_*.json; no backup script found | MED | HIGH | **7** | before real money |
| 7 | **Evidence merge is manual.** Actual-R/slippage live only in the VPS `fills.csv` + MT5 history export; the committee's go/no-go depends on a human remembering to merge them. Forgotten = decision on ETF-costed estimates. | FORENSIC_PIPELINE_AUDIT Phase 4 | MED | HIGH | **6** | before committee |
| 8 | **Broker response / retcode not validated as filled.** Order submission path should confirm MT5 retcode == DONE and detect partial/rejected fills, else state may record an entry that didn't fill (or vice-versa). Needs confirmation. | mt5_broker.py order path (unverified) | MED | HIGH | **6** | verify then fix |
| 9 | **Monitoring produces verdicts nobody is forced to act on.** `daily_check.py` writes ACTION/HEALTHY + exit code, but a red verdict has no escalation path (relies on the same silent-alert channel as #3). | scripts/ops/daily_check.py | MED | MED | **5** | mid |
| 10 | **DST static-offset fallback.** MT5 session offset is detected from a live tick, but falls back to a STATIC config value when no fresh tick (night/weekend) → sessions can fire ~1h off around DST changes. | mt5_broker.py:75 (_detect_utc_offset fallback) | MED (2×/yr) | MED | **5** | mid |
| 11 | **VPS clock/NTP drift.** All session windows are wall-clock; unmonitored clock drift fires sessions at wrong times. No NTP-sync check. | (no check found) | LOW | MED | **4** | mid |
| 12 | **GEX snapshot staleness.** S1's GEX gate reads `gex_history.csv`; if the snapshot isn't refreshed the gate decides on stale data (skip/allow wrongly). Refresh cadence unverified. | S1 GEX gate; gex_history.csv | MED | LOW-MED | **4** | mid |
| 13 | **No log rotation.** `trader.log` and per-venue logs grow unbounded on the VPS → eventual disk pressure. | logs/*.log; no RotatingFileHandler | LOW | LOW-MED | **3** | low |
| 14 | **GitHub Actions state is ephemeral.** The Alpaca-paper Actions path can't persist `risk_state` between runs → DD-throttle can't accumulate there (secondary/paper path only). | .github workflow; state files | LOW | LOW | **2** | low |
| 15 | **Dashboard :8501 reliability** — FIXED 2026-07-14 (conda streamlit resolution). Trade Explorer verified graceful on empty fills. | AI_INFRA.md; app.py | LOW | LOW | **1** | done |

---

## PRIORITIZED REMEDIATION CHECKLIST (no code changed here — this is the to-do)

### Tier 0 — before ANY real-money session (kill/availability/alerting)
- [ ] **#1 Arm the daily kill-switch.** Set `session_start_equity` to the true equity at each session start (or default it to live equity, not 0). A prop challenge dies on the daily loss limit first — this MUST fire. Verify with a forced-loss dry run.
- [ ] **#2 Add MT5 mid-session reconnect.** On `account_info()==None` / dropped terminal, re-`initialize()` with bounded retries instead of raising; alert if it stays down. Prevents a transient drop from crashing a whole session.
- [ ] **#3 Add a dead-man's switch for alerts.** On startup send a self-test ping; if the daily heartbeat is not received by an external checker (e.g. a phone reminder or a second channel), treat silence as failure. At minimum, log alert-send failures to a file that `daily_check` reads.
- [ ] **#4 External "did-it-run?" watchdog.** A cheap off-VPS check (cron on the Mac, or a healthchecks.io-style ping) that alarms if the VPS misses its expected session heartbeat. Removes the human-must-check dependency.

### Tier 1 — before real money / before the committee
- [ ] **#5 Rotate all exposed secrets** (MT5 password, Telegram token, Alpaca/Binance keys) and confirm none are in git history.
- [ ] **#6 Back up `state/` (and logs) off the VPS** — a daily copy of `risk_state_*.json` to git-ignored cloud or the Mac, so the DD-throttle peak baseline survives a VPS loss. Document the restore step.
- [ ] **#7 Automate the evidence merge** — a one-command pull of VPS `fills.csv` + MT5 history into the evidence set, run by the same daily job, so the committee never depends on a remembered manual export.
- [ ] **#8 Validate broker responses** — confirm the order path checks MT5 retcode == DONE, records actual fill price/qty, and flags partial/rejected fills (and that a failed order after 3 retries raises a LOUD alert).

### Tier 2 — hardening (this month)
- [ ] **#9 Escalate red monitoring verdicts** on a channel independent of the primary alert path.
- [ ] **#10 Make the MT5 DST offset DST-aware** (compute ET boundaries from a tz-aware conversion, not a static fallback).
- [ ] **#11 Add an NTP-sync check** to the daily health report.
- [ ] **#12 Verify/automate GEX snapshot refresh** so S1 never gates on stale data.

### Tier 3 — housekeeping
- [ ] **#13 Add log rotation** (RotatingFileHandler or logrotate on the VPS).
- [ ] **#14 Note** that the Actions/paper path can't accumulate DD-throttle state (accepted; VPS is authoritative).
- [x] **#15 Dashboard reliability** — done.

---
## The one-line verdict
The strategies could be perfect and **item #1 alone could still fail a challenge on
day one** — the daily kill-switch, the single most important operational safeguard for
a prop account, is currently inert by default. Fix Tier 0 before a single real-money
session; nothing in Tier 1-3 matters until #1-#4 are closed.
