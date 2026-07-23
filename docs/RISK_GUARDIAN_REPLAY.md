# Risk Guardian — Replay Report (monitor-only; enforcement NOT enabled)

Replay of the guardian's proposed limits against the real MT5 closed-trade history, using **only
information available at each trade's time** (verified by `test_replay_no_lookahead`). This
describes evidence; it does not enable enforcement.

## Config replayed (research defaults, config/guardian.env)
0.25%/trade · 0.50% open · **1% internal daily stop** · **3% internal total stop** ·
**3 consecutive losses → 24h cooldown** · no averaging into a losing instrument · SL required.

## Result on the exported window
| metric | actual account | with guardian |
|--|--|--|
| trades | 10 | 4 taken, **6 blocked** |
| net P&L | **−$545.41** | **−$0.30** |
| max drawdown | −$545.65 | **−$0.33** |
| loss avoided | — | **+$703.52** |
| winners skipped | — | −$158.41 |
| net P&L change | — | **+$545.11** |

**On this window, the proposed limits would have cut the drawdown from −$545 to ~breakeven** — by
blocking the trades that came *after* the loss cascade tripped the consecutive-loss + drawdown
rules, and by blocking re-entry into an already-losing instrument (the NAS100 repeats). No trade
was blocked using its own outcome.

## Honest caveats (do not over-trust this)
1. **Small sample:** only 10 closed trades in the export. This is not statistically robust.
2. **Stale/partial export:** the file ends 2026-07-14; the full 2-week drawdown was ~−$1,275 but
   the export only accounts for −$545. **Re-export MT5 history (last 30 days) and re-run** for the
   complete picture.
3. **Favorable clustering:** the guardian shines when losses cluster (its consecutive-loss rule
   catches them). If wins/losses were interleaved, it would skip more winners. It **did skip a
   $158 winner** here — that cost is real and will recur.
4. This is a *risk* result (smaller drawdown), **not** a *profit* result. The guardian cannot make
   a losing strategy win — it caps how much a bad stretch costs.

## Would prop limits still be breached?
With the guardian, the guarded-account max drawdown (−$0.33) stays far inside the 1% internal and
5% firm daily limits. Actual (−$545 ≈ −1.1%) already breached the 1% *internal* daily stop, which
is exactly the condition the guardian would have acted on.

## Recommendation (per spec — stop before enforcement)
1. Deploy in **monitor mode** now (logs/alerts only, never blocks live).
2. **Re-export the full 2 weeks** and re-run this replay.
3. Watch monitor-mode logs for a few live sessions.
4. **Only then**, with your explicit approval, enable `--mode enforce`.

No enforcement is enabled. The live bot is unmodified.
