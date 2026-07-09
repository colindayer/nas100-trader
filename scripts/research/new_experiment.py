"""
new_experiment.py -- create a queued experiment with a unique ID.

Usage:
    python scripts/research/new_experiment.py "DIX regime filter on 3 pillars" \
        --idea 2026-07-10-dark-pool-dix-regime-filter \
        --paper zarattini-2024-orb-stocks-in-play \
        --datasets "qqq_hourly_7y.csv, DIX daily CSV"

Creates research/queue/EXP-YYYYMMDD-NN-<slug>.md (never overwrites; NN auto-
increments). The note carries every required field: id, originating idea/paper,
hypothesis, success criteria, datasets, backtests, status, reviewer, Obsidian
links. Lifecycle is driven by promote_experiment.py. No production code touched.
"""
import argparse
import glob
import os
import re
import sys
from datetime import date

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
QUEUE = os.path.join(REPO, "research", "queue")

TEMPLATE = """---
type: experiment
id: {eid}
title: "{title}"
status: queued          # queued -> running -> gauntlet -> rejected | validated
created: {today}
idea: "{idea}"
paper: "{paper}"
datasets: "{datasets}"
script: ""              # set when the test script exists in research/experiments/
reviewer: ""            # REQUIRED (different model/person than author) before 'validated'
author: "{author}"
tags: [research, experiment]
---
# {eid} - {title}

## Origin
- Idea:  {idea_link}
- Paper: {paper_link}

## Hypothesis
_One falsifiable sentence._

## Success criteria (write BEFORE running -- the gauntlet, non-negotiable)
- [ ] IS/OOS walk-forward, costs ON
- [ ] OOS Sharpe > 0.5 and IS Sharpe > 0
- [ ] OOS max DD > -35%, >= 30 OOS trades
- [ ] |corr to QQQ weekly| < 0.3
- [ ] Positive/flat in the 2022 bear sub-period
- [ ] 6/6 IS/OOS split robustness (edge_hunt --sweep style)
- [ ] Extra criteria specific to this experiment:

## Datasets
{datasets_block}

## Backtests (fill as they run)
| date | script | split | IS Sharpe | OOS Sharpe | OOS DD | trades | corr | verdict |
|---|---|---|---|---|---|---|---|---|

## Verdict
_rejected (default) -> one line to FINDINGS/HUNT_LOG; validated -> reviewer sign-off
below, then human decision. NOTHING integrates during the 30-day stats window._

## Reviewer sign-off
- reviewer: (must differ from author)
- date:
- notes:

## Links
[[Research Index]] | [[02-Strategy-Research/Gauntlet|Gauntlet]] | [[00 Dashboard]]
"""


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    return s[:48] or "untitled"


def next_id():
    stamp = date.today().strftime("%Y%m%d")
    taken = []
    for d in ("queue", "experiments", "archive"):
        taken += glob.glob(os.path.join(REPO, "research", d, f"EXP-{stamp}-*.md"))
    ns = [int(m.group(1)) for p in taken
          if (m := re.search(rf"EXP-{stamp}-(\d+)", os.path.basename(p)))]
    return f"EXP-{stamp}-{(max(ns) + 1) if ns else 1:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("--idea", default="", help="idea note basename in research/ideas/ (no .md)")
    ap.add_argument("--paper", default="", help="paper note basename in research/papers/ (no .md)")
    ap.add_argument("--datasets", default="", help="comma-separated data sources")
    ap.add_argument("--author", default="research-ai", help="who authors this experiment")
    args = ap.parse_args()

    # warn (don't block) if origins don't exist yet
    for kind, name in (("ideas", args.idea), ("papers", args.paper)):
        if name and not os.path.exists(os.path.join(REPO, "research", kind, name + ".md")):
            print(f"WARNING: research/{kind}/{name}.md not found (link will be dangling)")

    eid = next_id()
    os.makedirs(QUEUE, exist_ok=True)
    path = os.path.join(QUEUE, f"{eid}-{slugify(args.title)}.md")
    if os.path.exists(path):
        print(f"REFUSED: {os.path.relpath(path, REPO)} exists.")
        sys.exit(1)

    ds = [d.strip() for d in args.datasets.split(",") if d.strip()]
    datasets_block = "\n".join(f"- {d}" for d in ds) if ds else "- (declare data sources here)"
    idea_link = f"[[{args.idea}]]" if args.idea else "(none -- create one with new_idea.py)"
    paper_link = f"[[{args.paper}]]" if args.paper else "(none)"

    with open(path, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(eid=eid, title=args.title.replace('"', "'"),
                                today=date.today().isoformat(),
                                idea=args.idea, paper=args.paper,
                                datasets=args.datasets.replace('"', "'"),
                                author=args.author,
                                idea_link=idea_link, paper_link=paper_link,
                                datasets_block=datasets_block))
    print(f"created {os.path.relpath(path, REPO)}  (id={eid}, status=queued)")


if __name__ == "__main__":
    main()
