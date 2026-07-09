"""
new_paper.py -- create a paper/resource review note in research/papers/.

Usage:
    python scripts/research/new_paper.py "Zarattini 2024 ORB Stocks in Play" --url https://ssrn.com/abstract=4729284
    python scripts/research/new_paper.py "Some book chapter" --authors "A, B" --year 2023

Creates an Obsidian-friendly review note with frontmatter, an honest-assessment
checklist (post-publication decay is the default expectation) and backlinks.
Never overwrites. No production code is touched. See research/README.md.
"""
import argparse
import os
import re
import sys
from datetime import date

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAPERS = os.path.join(REPO, "research", "papers")

TEMPLATE = """---
type: research-paper
title: "{title}"
authors: "{authors}"
year: {year}
url: "{url}"
status: unread          # unread -> reviewed -> idea-extracted | no-edge
created: {today}
tags: [research, paper]
---
# {title}

## Claim
_What the paper says works (strategy, instrument, reported Sharpe/returns)._

## Honest assessment checklist
- [ ] Out-of-sample or in-sample only?
- [ ] Transaction costs included? At what level?
- [ ] Sample period vs today — post-publication decay likely?
      (SSRN intraday-momentum precedent: +1.32 in-sample, -0.80 after publication)
- [ ] Retail-accessible, or needs AP/HFT/colo infrastructure?
- [ ] Prop-tradeable instruments (CFD/futures), or US single stocks only?

## Verdict
_no-edge (default) | idea extracted -> link the idea note below._

## Extracted ideas
- (create with `python scripts/research/new_idea.py "..."` and link here)

## Links
[[Research Index]] | [[02-Strategy-Research/Gauntlet|Gauntlet]] | [[00 Dashboard]]
"""


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    return s[:60] or "untitled"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title", help="paper title, quoted")
    ap.add_argument("--url", default="", help="source URL (SSRN/arXiv/...)")
    ap.add_argument("--authors", default="", help="author list")
    ap.add_argument("--year", default="", help="publication year")
    args = ap.parse_args()

    os.makedirs(PAPERS, exist_ok=True)
    path = os.path.join(PAPERS, f"{slugify(args.title)}.md")
    if os.path.exists(path):
        print(f"REFUSED: {os.path.relpath(path, REPO)} already exists (no overwrite).")
        sys.exit(1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(title=args.title.replace('"', "'"),
                                authors=args.authors.replace('"', "'"),
                                year=args.year or '""',
                                url=args.url,
                                today=date.today().isoformat()))
    print(f"created {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    main()
