# STARTUP

Every runner prints **live** diagnostics before doing anything. No status line in this system is a
hardcoded claim — each value is computed at call time.

```
py startup.py            # print the banner
py startup.py --json     # machine-readable
```

Automatically printed by `portfolio_mt5.py` in **all** modes (shadow, `--live`, `--demo-limited`).

## Fields
| field | source |
|--|--|
| version | `VERSION.json` + live `git rev-parse` |
| deployment | `deploy.verify()` — file-by-file SHA check against `MANIFEST.json` |
| modules | live import attempt of the 6 core modules |
| providers_configured | environment variables present on this machine |
| calendar_active | `calendar_feed.load()` — the provider actually returning data, plus forecast count |
| belief | `BeliefGraphV2` — live Research and Operational values |
| promotion | `promotion_pipeline_v2.evaluate()` — state, caps, blocking requirements |
| guardian | `guardian_bridge.guardian_ok()` — live evaluation |
| telegram | env presence + an explicit note that no runner emits alerts yet |
| broker | `mt5.account_info()` — DEMO/REAL, login, server, equity |

## Reading it
```
guardian    BLOCK (GUARDIAN_SNAPSHOT_BAD)
```
Not an error: the guardian ran and could not obtain a usable MT5 snapshot, so it refused. **Fail-closed
is the correct outcome.** `GUARDIAN_UNAVAILABLE` *would* be a real problem — the module itself is missing.

```
calendar_active   faireconomy: 71 events, 53 with forecast
```
The provider chain resolved to FairEconomy and it is returning consensus forecasts.
