"""
promote_experiment.py -- drive an experiment through its lifecycle.

    queued -> running -> gauntlet -> rejected | validated
    (research/queue/)  (research/experiments/)   (research/archive/)

Usage:
    python scripts/research/promote_experiment.py EXP-20260710-01 --to running
    python scripts/research/promote_experiment.py EXP-20260710-01 --to gauntlet
    python scripts/research/promote_experiment.py EXP-20260710-01 --to rejected
    python scripts/research/promote_experiment.py EXP-20260710-01 --to validated --reviewer "GLM-review"

Rules enforced (from AI_OPERATING_SYSTEM.md):
- transitions must follow the lifecycle order (no queued -> validated jumps)
- 'validated' REQUIRES --reviewer, and reviewer must differ from author
- rejected/validated notes move to research/archive/ (the graveyard is memory)
- never overwrites; only the note's frontmatter status/reviewer lines change
- NO integration into the live path happens here -- validated only means
  "cleared for the human decision". Production stays untouched.
"""
import argparse
import glob
import os
import re
import sys
from datetime import date

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIRS = {"queued": "queue", "running": "experiments", "gauntlet": "experiments",
        "rejected": "archive", "validated": "archive"}
ORDER = ["queued", "running", "gauntlet", "rejected", "validated"]
ALLOWED = {  # from-status -> allowed targets
    "queued":   {"running"},
    "running":  {"gauntlet", "rejected"},
    "gauntlet": {"rejected", "validated"},
}


def find_note(eid):
    hits = []
    for d in set(DIRS.values()):
        hits += glob.glob(os.path.join(REPO, "research", d, f"{eid}-*.md"))
    return hits


def get_field(text, key):
    m = re.search(rf"^{key}:\s*\"?([^\"\n]*)\"?\s*$", text, re.M)
    return m.group(1).strip() if m else ""


def set_field(text, key, value):
    return re.sub(rf"^({key}:).*$", rf'\1 "{value}"', text, count=1, flags=re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eid", help="experiment id, e.g. EXP-20260710-01")
    ap.add_argument("--to", required=True, choices=ORDER[1:])
    ap.add_argument("--reviewer", default="", help="required for --to validated")
    args = ap.parse_args()

    hits = find_note(args.eid)
    if not hits:
        print(f"NOT FOUND: no note for {args.eid} in queue/experiments/archive")
        sys.exit(1)
    if len(hits) > 1:
        print(f"AMBIGUOUS: {args.eid} exists in multiple stages: {hits}")
        sys.exit(1)
    src = hits[0]
    text = open(src, encoding="utf-8").read()
    cur = get_field(text, "status") or "queued"
    cur = cur.split()[0]  # strip inline comment remnants

    if args.to not in ALLOWED.get(cur, set()):
        print(f"REFUSED: illegal transition {cur} -> {args.to} "
              f"(allowed from {cur}: {sorted(ALLOWED.get(cur, []))})")
        sys.exit(1)

    if args.to == "validated":
        if not args.reviewer:
            print("REFUSED: --reviewer is required for 'validated' "
                  "(author != reviewer rule).")
            sys.exit(1)
        author = get_field(text, "author")
        if author and args.reviewer.strip().lower() == author.strip().lower():
            print(f"REFUSED: reviewer '{args.reviewer}' equals author '{author}'.")
            sys.exit(1)
        text = set_field(text, "reviewer", args.reviewer)

    text = re.sub(r"^status:.*$", f"status: {args.to}          # promoted {date.today().isoformat()}",
                  text, count=1, flags=re.M)

    dest_dir = os.path.join(REPO, "research", DIRS[args.to])
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    if os.path.abspath(dest) != os.path.abspath(src) and os.path.exists(dest):
        print(f"REFUSED: {os.path.relpath(dest, REPO)} already exists.")
        sys.exit(1)

    open(src, "w", encoding="utf-8").write(text)
    if os.path.abspath(dest) != os.path.abspath(src):
        os.replace(src, dest)
    print(f"{args.eid}: {cur} -> {args.to}  ({os.path.relpath(dest, REPO)})")
    if args.to == "rejected":
        print("Remember: add one line to FINDINGS.md/HUNT_LOG.md (the graveyard is memory).")
    if args.to == "validated":
        print("Cleared for HUMAN decision only. No integration during the 30-day window.")


if __name__ == "__main__":
    main()
