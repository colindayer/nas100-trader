# Root Cause Report — BTCTREND simultaneous long+short (Pepperstone MT5 hedge account)

Observed (2026-07-20): BUY 0.04 + BUY 0.01 + SELL 0.01 BTCUSD, all comment `BTCTREND`.
Net long, opposite leg alive. Investigation classification: **BUG (logic defect on hedge
accounts) + DEPLOYMENT GAP** — not intended behavior, not a race, not a broker rejection.

## Strategy intent (from the codebase — not guessed)

`run_btc_trend` is a **long/flat** vol-targeted Donchian 20/10 rebalancer: `p ∈ {0,1}`
in the signal loop, `target_qty ≥ 0` always, comments in the code state "BTCTREND is
long/flat by design -- it must NEVER hold a net short." **Intent = A: exactly one
directional exposure. Hedging is never intended.**

## Sequence of events (from the evidence-bridge execution logs — timestamps server time)

```
Jul16 01:48  OLD CODE   sell 0.05 sent as plain TRADE_ACTION_DEAL      ── hedge account
             │          ("NAKED ORDER BTCTREND" + "MT5 FILL sell 0.05      opens SHORT
             │           ticket=342163006" in the log = pre-fix path)      342163006
Jul17 01:48  OLD CODE   same defect again: sell 0.01 → SHORT 342998200
             │          (state file said "reduced"; broker disagreed)
Jul17–19     R1 repair  emergency SL attached to ALL BTC positions incl. the short
             │          (SL 76761.76 on the sell = R1 ensure_btc_protection, deployed)
Jul20 11:48  R1 CODE    buy 0.04 with SL — R1 predates the hedging fix, so the buy
             │          path never examined opposite legs
Jul20 14:03  R1 CODE    buy 0.01 top-up (equity/price moved the vol target ≥ tolerance;
             │          two runs that day, both legitimate rebalances, not duplicates)
NOW          long 0.05 + short 0.01, both protected, hedge alive.
```

## Root cause (three layers)

1. **Primary defect** (`live_trader.py` pre-`2c2f432`): on a **hedge-mode** account,
   MT5 `order_send(TRADE_ACTION_DEAL, SELL)` **without** `position=<ticket>` opens a new
   opposite position instead of reducing — hedge semantics were not respected. Combined
   with state-file-as-truth (`btc_trend_state.json` recorded the *intended* qty), the
   strategy believed it had reduced.
2. **Deployment gap**: the fix (`2c2f432`, 2026-07-16 — broker-as-truth `net_qty` +
   ticket-targeted `close_into`) was committed locally but **never pushed** (4 commits
   behind `origin/main` at investigation time). The VPS demonstrably ran the old sell
   path on Jul 16/17 (the fixed code cannot emit "NAKED ORDER … sell" lines).
3. **Residual defects found in the fix itself during this investigation**:
   - **D-A**: `close_into` was capped at the rebalance delta — a short larger than the
     day's buy delta would only be *partially* closed (partial-close artefact risk).
   - **D-B**: no verify-then-abort — if closing the short failed (rejection, context
     busy, timeout), the buy was still submitted, *creating* the hedge.
   - **D-C** (red-team RT5): ownership matched by MT5 `comment` only — brokers rewrite
     comments on partial closes ("to #…"), orphaning the leg from future management.

Failure modes checked and excluded: close order rejection (no MT5 REDUCE/CLOSE FAIL in
any log — no close was ever *attempted* by the old code), trade-context-busy, timeout,
magic-number filtering (all strategies share magic 770001; ownership is comment/ticket
based), race between runs (runs are 2h+ apart, lock-file guarded), duplicate signal
(the two Jul 20 buys are distinct legitimate rebalances).

## Fix applied (smallest safe correction — exactly the mandated behavior)

`mt5_broker.close_into(symbol, qty_units, side, tag, tickets=None)`:
- `qty_units=None` → close the **entire** matching side (fixes D-A)
- `tickets=[…]` → positions owned via the state-file **ticket registry** are matched
  even when the broker rewrote the comment (fixes D-C)
- unbounded-mode lot arithmetic hardened (no float-inf conversion)

`live_trader.run_btc_trend`:
- **Before any BUY**: close **ALL** owned short legs → **re-query the broker and verify
  none remain** → if any survive: log + alert + **ABORT the entry** (fixes D-B). After
  a successful flatten, the remaining delta is **recomputed from broker truth** before
  sizing the buy.
- Reductions (sell path) unchanged: partial closes into long tickets ARE the vol-target
  rebalance; a SELL order is never submitted on MT5 (long/flat invariant).
- `btc_trend_state.json` now carries `tickets`: fills append, closed tickets are pruned
  against the broker each run.
- Foreign positions (other comments, not in the registry) are never touched — NAS100,
  other strategies, and manual trades are structurally out of scope of `close_into`.

Self-healing: on the next `btctrend` run after deployment, the buy path flattens the
0.01 short before doing anything else (or aborts loudly if the broker refuses).

## Tests (7 new; file total 26; with emergency-protection + reconnect: 42/42 OK)

Long→short-flattening reversal, short-leg close failure → zero-closed (caller aborts),
partial close covered by rerun, broker rejection honesty, comment-rewrite ownership via
registry, foreign-position safety, repeated-run idempotence, netting semantics,
delta-capped reduction never opens a short, source-locks for flatten-verify-abort order.

## Deployment (required — the fix only exists once this happens)

```
Mac:  cd ~/nas100_backtest && git push origin main
VPS:  cd C:\...\nas100-trader && git pull
      python live_trader.py --broker mt5 --session btctrend   (watch: "closed opposing
      short leg(s)" then a single net-long book in the terminal)
```
