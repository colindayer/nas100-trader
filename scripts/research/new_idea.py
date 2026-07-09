"""
new_idea.py -- create a research idea note in research/ideas/.

Usage:
    python scripts/research/new_idea.py "Dark-pool DIX regime filter"
    python scripts/research/new_idea.py "My idea" --source "ChatGPT brainstorm"

Creates an Obsidian-friendly note with frontmatter, the gauntlet checklist and
backlinks. Never overwrites: if the slug exists, it aborts and tells you.
No production code is touched. See research/README.md.
"""
import argparse
import os
import re
import sys
from datetime import date

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IDEAS = os.path.join(REPO, "research", "ideas")

TEMPLATE = """---
type: research-idea
title: "{title}"
status: idea            # idea -> experiment -> gauntlet -> rejected | validated
created: {today}
source: "{source}"
tags: [research, idea]
---
# {title}

## Hypothesis
_One sentence: what edge, on what instrument, why should it exist (mechanism)?_

## Graveyard check (do FIRST)
- [ ] Not already rejected in `FINDINGS.md` / `HUNT_LOG.md` /
      [[02-Strategy-Research/Rejected Ideas|Rejected Ideas]]

## A-priori parameters (write BEFORE testing — no grid-search-then-report-best)
-

## Gauntlet plan
- [ ] Standalone script in `research/experiments/` (never the live path)
- [ ] IS/OOS walk-forward, costs ON
- [ ] OOS Sharpe > 0.5 and IS Sharpe > 0, OOS DD > -35%, >= 30 trades
- [ ] |corr to QQQ weekly| < 0.3
- [ ] Works in bear sub-period (2022)
- [ ] Robust across 6/6 IS/OOS splits (`edge_hunt.py --sweep`)

## Result
_status + one honest paragraph. If rejected: one line to FINDINGS/HUNT_LOG and stop._

## Links
[[Research Index]] | [[02-Strategy-Research/Gauntlet|Gauntlet]] | [[00 Dashboard]]
"""


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    return s[:60] or "untitled"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title", help="idea title, quoted")
    ap.add_argument("--source", default="manual", help="where the idea came from")
    args = ap.parse_args()

    os.makedirs(IDEAS, exist_ok=True)
    path = os.path.join(IDEAS, f"{date.today().isoformat()}-{slugify(args.title)}.md")
    if os.path.exists(path):
        print(f"REFUSED: {os.path.relpath(path, REPO)} already exists (no overwrite).")
        sys.exit(1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(title=args.title.replace('"', "'"),
                                today=date.today().isoformat(),
                                source=args.source.replace('"', "'")))
    print(f"created {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    main()
