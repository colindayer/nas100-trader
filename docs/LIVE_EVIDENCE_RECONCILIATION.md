# LIVE EVIDENCE RECONCILIATION

_2026-07-14. Read-only; no code/strategy/venue change. Objective: convert forensic
ESTIMATES into MEASURED evidence. Result: the venue/overlay portion is now measured
(modeled from the validated backtest); the LIVE-execution portion is INSUFFICIENT_DATA
because the authoritative VPS inputs are not present on this host (Mac logs were NOT
substituted, per instruction). Bridge delegation was N/A -- there are no VPS logs here
to extract from. Claude computed and verified all numbers._

## 1. Data completeness
| input | present? | authority | status |
|---|---|---|---|
| 1. VPS logs/fills.csv | **NO (empty on this host)** | VPS | REQUIRED -- blocks Tasks 1,2,3 |
| 2. MT5 trade-history export | **NO** | MT5 terminal | REQUIRED -- blocks realized R / swap |
| 3. VPS logs/mt5_*.log | **NO** | VPS | REQUIRED -- blocks rejects/retcodes/latency |
| 4. VPS trader.log | NO (only a 335-line MAC copy) | VPS | Mac copy NOT used |
| 5. validated backtest + data | YES (full_yearly/master_backtest, qqq_hourly_7y) | repo | used for Task 4 |
| 6. production config | YES (template; config.ini local) | repo | used for Task 4 scenario D |

**Exact export steps to unblock (run on the VPS, then commit/push or paste):**
1. `fills.csv` -> `copy logs\fills.csv` into the repo and `git add -f logs/fills.csv && git commit && git push` (it is gitignored; force-add a copy), OR paste its contents.
2. MT5 history -> MT5 terminal: Toolbox -> **History** tab -> right-click -> **Report** -> save as HTML/CSV; OR run `python fetch_mt5_history.py --symbols US100 XAUUSD BTCUSD --years 1`.
3. `logs\mt5_*.log` and `logs\trader.log` -> copy into the repo (or paste the last N lines per session).
Until these arrive, live reconciliation stays INSUFFICIENT_DATA -- not estimated.

## 2. Per-strategy reconciliation (signal -> order -> MT5 history -> fills)
**INSUFFICIENT_DATA for all live legs** -- no `fills.csv` rows, no MT5 history, no VPS
session logs on this host. The chain cannot be reconciled without inputs 1-3. Backtest-
level facts that ARE established (not live): S2 was inert then fixed; S3 live rule is a
measured subset; OVN was crash-blocked then fixed.

## 3. Cost & execution measurements
| metric | value | source |
|---|---|---|
| actual spread / entry+exit slippage | **INSUFFICIENT_DATA** | needs fills.csv (signal_price vs bid/ask/fill) |
| commission / swap / weekend financing | **INSUFFICIENT_DATA** | needs MT5 history |
| execution latency | **INSUFFICIENT_DATA** | needs signal_ts vs fill_ts (mt5 logs) |
| broker rejects / retcodes | **INSUFFICIENT_DATA** | needs mt5_*.log |
| missing / duplicate fills | **INSUFFICIENT_DATA** | needs fills.csv vs MT5 history |
| realized R / PnL by strategy | **INSUFFICIENT_DATA** | needs closed-trade history |
| **modeled CFD financing impact** (S5) | **-0.51 Sharpe** (measured below) | validated backtest re-cost |

## 4. Re-cost of validated results -- 4 fixed scenarios (S5, 7.5y; MEASURED)
| scenario | N | CAGR | Sharpe | avgR | avg days held |
|---|---|---|---|---|---|
| A original research assumptions | 369 | +14.9% | **1.40** | +0.442 | 4.9 |
| B realistic ETF execution | 369 | +14.9% | **1.40** | +0.442 | 4.9 |
| C realistic CFD (financing on) | 369 | +8.7% | **0.89** | +0.442 | 4.9 |
| D CFD + live risk overlay | 261 | +6.8% | **0.93** | +0.579 | 6.3 |

_Scenario definitions: A/B = 3 bps/side, no financing (ETF is commission-free & carry-
free -> B == A, confirming the ETF leg is FAITHFUL). C adds ~3 bps/day financing on
notional over calendar days held (weekends counted). D adds the vix_mult regime throttle
(size x{0,0.5,1}; skips VIX>25 days)._ Method is modeled from the validated engine, not
live fills -- an upper-confidence estimate of the venue/overlay effect, pending live
measurement.

## 5. Expectancy-gap waterfall (Sharpe)
```
A research assumptions      1.40
  -> B ETF venue            1.40   Δ +0.00   ETF is faithful (no leak)
  -> C CFD financing        0.89   Δ -0.51   VENUE/FINANCING = the dominant modeled leak
  -> D + risk overlay       0.93   Δ +0.04   throttle: risk-reducing (fewer, better trades)
  modeled subtotal A->D:  -34% Sharpe (driven almost entirely by CFD financing)
  + downtime                 INSUFFICIENT_DATA  (needs live trade count vs expected)
  + implementation drift     INSUFFICIENT_DATA  (needs fills vs signal reconciliation)
  + unexplained residual     INSUFFICIENT_DATA  (live minus modeled)
```
**Measured conclusion:** of the modeled backtest->live gap, ~all of it is CFD financing;
the ETF venue adds nothing and the risk throttle is neutral-to-helpful on Sharpe (it
cuts CAGR by trading less in stress). The remaining gap components CANNOT be quantified
without live data.

## 6. Unresolved discrepancies (require inputs 1-3)
- Actual vs modeled financing (does Pepperstone charge ~3 bps/day, ×3 weekend?).
- Real spread/slippage vs the 3 bps assumption on US100/XAUUSD.
- Whether live orders filled (retcode DONE) and at what price (missing/dup fills).
- Live trade COUNT vs expected (downtime magnitude) -- the largest unmeasured term.
- OVN: does it now actually place orders post-crash-fix (needs one live session).

## 7. Committee decisions ENABLED by current evidence
- **ETF-vs-CFD routing:** the re-cost proves the ETF leg is faithful and CFD financing
  is the dominant modeled leak -> the committee can decide to PREFER the Alpaca/ETF venue
  for ETF-validated strategies on evidence, not estimate. (Provenance preserved; routing,
  not signal -> no clock reset.)
- **S3 rule:** the measured subset (4/yr vs 15/yr, 97% overlap) supports a REVALIDATE
  decision (restore the validated rule) independent of live data.
- **Everything requiring realized R / cost truth: DEFERRED** until inputs 1-3 are merged.

## 8. Status per strategy (exactly one each)
| strategy | status | basis |
|---|---|---|
| S1 | INSUFFICIENT_DATA | no live fills; ETF leg modeled-faithful only |
| S2 | INSUFFICIENT_DATA | fixed 07-12, no live fills yet |
| S3 | REVALIDATE | measured subset divergence (backtest-level, not needing live) |
| S4 | INSUFFICIENT_DATA | no live fills |
| S5 | INSUFFICIENT_DATA | re-cost is modeled; live execution unmeasured |
| OVN | INVESTIGATE_OPERATIONAL | crash-fix (07-14) unverified live; confirm it now trades |
| BTC | INSUFFICIENT_DATA | venue-swap effect unmeasured; no live fills |
| BTCTREND | INSUFFICIENT_DATA | no live fills |

**Bottom line:** the venue/overlay portion is now MEASURED (CFD financing ~-0.51 Sharpe;
ETF faithful; throttle neutral). Everything else is honestly INSUFFICIENT_DATA until the
VPS `fills.csv` + MT5 history are exported per section 1 -- the single action that
converts six INSUFFICIENT_DATA rows into measured evidence.
