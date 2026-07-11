# RESEARCH BACKLOG -- discovery FROZEN (2026-07-12)

_Every active research item, exactly one status. No new papers, no new experiments
until the evidence month closes (~2026-08-11). Statuses: READY (could run now,
post-freeze) | SHADOW (accumulating forward evidence) | WAITING (blocked on a
condition) | REJECTED (graveyard) | ARCHIVED (done, no action)._

## Experiments
| item | status | note |
|---|---|---|
| EXP-20260711-01 VIX term-structure gate | **SHADOW** | validated-for-forward-shadow after adversarial review; gate values logged daily; needs a backwardation episode to differentiate |
| ETF universe expansion (9 survivor streams) | **SHADOW** | review-validated; shadow_signals.csv accumulating; pre-registered verdict rule frozen (>=15 days, 40% rate, corr<0.5) |
| EXP-20260710-01 DIX regime filter | **REJECTED** | closed via lifecycle without running: superseded by the FINDINGS DIX rejection (sign-unstable IS/OOS flip) -- running it would re-test the graveyard |
| S5 re-entry divergence replay | **ARCHIVED** | done 07-12: KEEP verdict, divergence accepted, tripwire registered |
| ATR compression filter | **REJECTED** | adversarial review 07-12 (look-ahead + post-hoc threshold) |

## Ideas
| item | status | note |
|---|---|---|
| DXY < 200dMA gate | **WAITING** | 6/6 vs baseline but era-lumpy, -58% trades; blocked on: post-window adversarial battery (LOYO, 2x costs, episode attribution) |
| dark-pool DIX idea note | **REJECTED** | same graveyard entry as the experiment above |
| vix-term-structure idea note | **ARCHIVED** | graduated into EXP-20260711-01; the shadow carries it now |
| intraday-return momentum (RFS 2026) | **REJECTED** | 07-12 review: real mechanism, breadth-starved + CFD-dead; reopen condition = broad single-stock book |
| Industry-rotation TSMOM | **WAITING** | blocked on: an Alpaca slow-sleeve decision post-window (Part C economics currently against) |
| Funding carry | **WAITING** | shelved years-equivalent: real edge, FTX-tail risk; blocked on a tail mitigation that does not exist yet |
| TensorTrade | **ARCHIVED** | DEFER verdict on file; venv recipe preserved in the evaluation doc |

## Router tasks (research lane)
| item | status | note |
|---|---|---|
| TASK-...-01 review DIX result table | **REJECTED** | moot -- parent experiment closed above |
| TASK-...-02 summarize Moskowitz paper | **WAITING** | reading-lane work for any idle session; not evidence-critical |
| TASK-...-03 ops digest wiring | **ARCHIVED** | superseded by evidence_report + ledger |
| TASK-...-04/05/06 (import/index/obsidian chain) | **ARCHIVED** | completed 07-10, execution logs in-body |
| TASK-20260712-01/02/03 daily evidence trio | **SHADOW** | the recurring evidence-month heartbeat (shadow log, macro state, ledger line) |

## Paper notes
| item | status | note |
|---|---|---|
| Fassas 2019 (VIX term structure) | **ARCHIVED** | consumed by EXP-01 |
| Gilchrist-Zakrajsek 2012 | **WAITING** | revisit only if the book ever trades at daily+ frequency (frequency mismatch on file) |
| Zarattini ORB 2024 / Moskowitz 2012 | **ARCHIVED** | foundational references, fully absorbed |

## READY column: deliberately EMPTY
Nothing is READY by design -- discovery is frozen. The first candidates to move to
READY when the freeze lifts (post month-end report): (1) DXY battery, (2) whatever
the shadow verdicts promote to the post-window review queue.

## Standing totals
SHADOW 3 | WAITING 5 | REJECTED 5 | ARCHIVED 8 | READY 0
