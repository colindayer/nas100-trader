# OPERATOR_RUNBOOK

## Morning startup (in order — stop at the first failure)
```powershell
cd C:\Users\Administrator
py deploy.py --verify            # COMPLETE
py deploy.py --scan-executors    # CLEAN
py healthcheck.py                # 0 critical
py startup.py                    # read every line
py portfolio_mt5.py --config funded   # shadow book
```

## Health checks
`py healthcheck.py` — 16 subsystems. `*` marks critical; **any critical FAIL = do not trade.**
`WARN` on environment/telegram is acceptable. `SKIP` on broker means MT5 was unreachable.

## Provider verification
```powershell
py -c "import sys;sys.path.insert(0,'.');from market_intel import calendar_feed as c;e=c.load();print(len(e),'events,',sum(1 for x in e if x.forecast is not None),'forecasts')"
```
Expect ~70 events, ~50 forecasts. **0 events** → run `py -c "...faireconomy_provider as f;f.diagnose()"`
once (it is rate-limited; do not loop).

## MT5 verification
`startup.py` must show `DEMO <login> @ <server> | equity`. **REAL means stop immediately.**

## Guardian verification
`startup.py` line `guardian`. `ALLOW` = ok. `BLOCK (GUARDIAN_SNAPSHOT_BAD)` = ran but no usable
snapshot — correct fail-closed. `GUARDIAN_UNAVAILABLE` = module missing — **fix before trading**.

## Promotion verification
Expect `LIMITED_DEMO_APPROVED`, caps `1pos/0.10%`. Anything higher without a recorded promotion
decision is a governance incident — halt and investigate.

## Belief verification
Research ≈ 0.61, Operational rises only with demo evidence. **A sudden change with no new evidence
means state corruption** — check `registry/safety_state_audit.jsonl`.

## Telegram verification
`configured` only means env vars are set. **No runner currently emits alerts.** Absence of alerts is
not evidence of health.

## Market Intelligence verification
Dashboard shows regime, kill zones, structure, calendar countdown. Compare the calendar timestamp to
now — stale cache is served without a max age (V-07 open).

## How to stop trading safely
1. MT5 → **Algo Trading** button → grey.
2. Disable scheduled tasks: `Disable-ScheduledTask -TaskName "<name>"`.
3. Persistent halt (survives reboot):
```powershell
py -c "import sys;sys.path.insert(0,'.');from execution_safety import safety_state as s;s.halt('operator stop')"
```
4. **Do not auto-close positions.** Use the manual close checklist in `INCIDENT_RESPONSE.md`.

## How to restart after failure
1. Read `registry/safety_state_audit.jsonl` — find the HALT event and its reason.
2. Resolve the underlying cause (orphan position, naked stop, corrupt state).
3. `py deploy.py --verify` + `py healthcheck.py`.
4. Clear the halt **explicitly**:
```powershell
py -c "import sys;sys.path.insert(0,'.');from execution_safety import safety_state as s;s.clear_halt('human:colindayer','root cause: <what you fixed>')"
```
5. Shadow run. Only then consider resuming.
**There is no automatic un-halt anywhere in the system, by design.**
