# PORTFOLIO_DEMO_READINESS

**Verdict: NO-GO for automatic execution. GO for dry-run.**

Execution stays disabled until the dry-run is run on the VPS and its preflight prints GO. Two of
the required checks can only be evaluated against the live terminal and have never been observed.

---

## The frozen strategy (production, fixed)

| | |
|---|---|
| universe | GOLD, SILVER, OIL, COPPER, NAS100, SP500 — six only |
| signal | `portfolio_mt5.target_weights(sleeves=('TREND',))`, 252-day lookback |
| sizing | 5% annualised vol target, max_leverage 3.0 |
| execution | daily rebalance, 0.005 no-trade band |
| exit | target-weight reduction, zero, or sign reversal — **nothing else** |
| safeguard | 15% catastrophe stop, broker-side, disaster protection only |
| **not present** | no CARRY, no fixed TP, no performance trailing stop |
| reference | Sharpe 0.653 · maxDD −10.19% · ~84% pass · ~5.5% breach · ~438 median days |

---

## Verification status

| check | status | evidence |
|---|---|---|
| Live `target_weights()` == frozen backtest | **PASS** | 7 named dates, max diff **0.000e+00** |
| No look-ahead | **PASS** | future perturbation moved weights by 0.0e+00 |
| Universe is the frozen six, TREND only | **PASS** | asserted in test |
| Restart cannot duplicate an order | **PASS** | deterministic intent id, stable across runs, distinct by side and size |
| No-trade band suppresses small / permits large | **PASS** | 0.0020 held, 0.2000 traded |
| Sign reversal and zeroing classified as CLOSE | **PASS** | both `REDUCE_OR_CLOSE`, `crosses_zero` flagged |
| Closes ordered before opens | **PASS** | frees margin first |
| Held state from broker, foreign magic ignored | **PASS** | 9.99-lot foreign position excluded |
| `positions_get()` failure aborts (fail-closed) | **PASS** | raises instead of assuming flat |
| No TP / trailing stop in executable code | **PASS** | AST scan of code with docstrings stripped |
| Deployment manifest | **PASS** | 40 files |
| **Dry-run against FTMO demo** | **NOT RUN** | requires the VPS terminal |
| **Broker metadata (real spread/tick/contract)** | **NOT OBSERVED** | only readable live |
| **Telegram on this strategy id** | **NOT PROVEN** | proven for the old runner, not this one |
| **Guardian approval for `portfolio_frozen_v1`** | **NOT GRANTED** | no contract registered for this id |

---

## The design decision the tests forced

The no-trade band is **path-dependent**. Rebuilding it by recomputing history leaves a 5.1e-04
weight error even with 504 days of warm-up, and 3.9e-02 with 20 days. It does not converge.

So the live loop never recomputes held state. It reads **actual broker positions** and converts
them to weights. A restart is therefore self-healing, and the bot cannot silently disagree with
the broker about what it owns. This was discovered by the parity test, not assumed.

---

## Why NO-GO

Four required gates have never been observed, and three of them are unobservable off the VPS:

1. **Dry-run never executed against the live terminal.** The plan builder is tested against mocks
   only. Mocks prove logic; they do not prove the broker agrees.
2. **Broker metadata unverified.** Real spread, tick size, tick value, contract size, minimum stop
   distance and freeze level for FTMO's `XAUUSD / XAGUSD / USOIL.cash / XCUUSD / US100.cash /
   US500.cash` have never been read. Position sizing depends on `trade_contract_size`, and a wrong
   value mis-sizes every order.
3. **No strategy contract for `portfolio_frozen_v1`.** Guardian cannot approve an id that does not
   exist. Registering it is a deliberate act, not something this file should do silently.
4. **Telegram unproven for this runner.** The alert chain was proven for `portfolio_multisleeve`.

**No scheduled task has been installed or modified.** Nothing trades automatically.

---

## Rollback

```powershell
Disable-ScheduledTask -TaskName "QuantOS Shadow"
Move-Item registry\frozen_plan.json registry\frozen_plan.rollback.json -Force
```

The frozen loop writes only `registry/frozen_plan.json` and sends no orders in `--dry-run`, so
rollback is removing the plan file and disabling the task. No broker state is touched.

---

## The gate to GO

Run the dry-run. If its preflight prints **GO** and the order plan is sane — six symbols resolved,
lots consistent with 5% vol on 100k, spreads plausible — then the remaining work is registering the
strategy contract and proving Telegram, after which limited demo can be enabled with the first five
fills auto-audited.

If preflight prints **NO-GO**, the printed check list names the exact failing gate.
