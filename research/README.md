# Research OS v1

The intake layer for the research pipeline (AI_OPERATING_SYSTEM.md section 6).
Nothing here touches production: ideas and papers live as markdown, experiments
as standalone scripts. **The only exit from this folder into the live path is
through the Gauntlet + Reviewer + human sign-off.**

## Layout

```
research/
  ideas/         one note per trading idea (from any AI/human brainstorm)
  papers/        one note per paper/resource reviewed (SSRN, arXiv, books)
  experiments/   standalone test scripts + their result notes
  README.md      this file
```

## Creating entries

```
python scripts/research/new_idea.py  "Dark-pool DIX regime filter"
python scripts/research/new_paper.py "Zarattini 2024 ORB Stocks in Play" --url https://ssrn.com/abstract=4729284
```

Both create a pre-filled, Obsidian-friendly note (frontmatter + backlinks +
checklist) and never overwrite an existing note.

## Lifecycle of an idea (statuses used in frontmatter)

`idea` -> `experiment` (script written in research/experiments/) -> `gauntlet`
-> `rejected` (default outcome — log one line in HUNT_LOG/FINDINGS, move on)
or `validated` (Reviewer + human sign-off required before ANY integration).

## Rules (inherited from the AI Operating System)

- Research NEVER edits `live_trader.py`, brokers, or validated constants.
- Check the graveyard FIRST (`FINDINGS.md`, `HUNT_LOG.md`,
  [[02-Strategy-Research/Rejected Ideas|Rejected Ideas]]) — ~30 ideas are already
  dead; do not re-test them.
- A backtest PASS on one split is split-luck. The bar is 6/6 splits
  (`edge_hunt.py --sweep`) plus the full gauntlet (IS/OOS, costs, |corr|<0.3, regime).
- During the 30-day statistics window nothing graduates to live regardless of results.

Backlinks: notes here link into the vault ([[Research Index]], [[02-Strategy-Research/Gauntlet|Gauntlet]])
so the Obsidian graph spans repo research and vault knowledge.
