#!/usr/bin/env python3
"""
research_dashboard.py — Generate a markdown dashboard for the research pipeline.

Shows the full state of research: queued ideas, running experiments, validated/
rejected work, imported papers, research velocity, and recent AI activity.

Usage:
    python scripts/research/research_dashboard.py              # write to file
    python scripts/research/research_dashboard.py --print       # stdout
    python scripts/research/research_dashboard.py --dry-run     # summary only
    python scripts/research/research_dashboard.py --vault       # also write to vault

Never touches production code. Read-only over the research tree.
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAPERS_DIR = os.path.join(REPO, "research", "papers")
IDEAS_DIR = os.path.join(REPO, "research", "ideas")
QUEUE_DIR = os.path.join(REPO, "research", "queue")
EXPERIMENTS_DIR = os.path.join(REPO, "research", "experiments")
ARCHIVE_DIR = os.path.join(REPO, "research", "archive")
RESULTS_DIR = os.path.join(REPO, "research", "results")
CHANGELOG = os.path.join(REPO, "docs", "AI_CHANGELOG.md")
VAULT_DASHBOARD = os.path.join(REPO, "vault", "02-Strategy-Research", "Research Dashboard.md")

DASHBOARD_OUTPUT = os.path.join(RESULTS_DIR, "research_dashboard.md")


# ── Frontmatter parser ─────────────────────────────────────────────────

def parse_frontmatter(path):
    """Parse YAML frontmatter from a markdown file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}, ""

    fm = {}
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if "#" in val and not val.startswith('"'):
                    val = val.split("#")[0].strip()
                val = val.strip('"').strip("'")
                fm[key] = val
    return fm, text


# ── Data collectors ────────────────────────────────────────────────────

def collect_notes(directory, note_type):
    """Collect all markdown notes from a directory (excluding READMEs)."""
    notes = []
    for path in sorted(glob.glob(os.path.join(directory, "*.md"))):
        basename = os.path.basename(path)
        if basename.startswith("README"):
            continue
        fm, text = parse_frontmatter(path)
        notes.append({
            "path": path,
            "rel_path": os.path.relpath(path, REPO),
            "basename": os.path.splitext(basename)[0],
            "type": note_type,
            "fm": fm,
            "title": fm.get("title", basename),
            "status": fm.get("status", "unknown").split()[0],
            "created": fm.get("created", ""),
            "tags": fm.get("tags", ""),
        })
    return notes


def collect_hunt_entries():
    """Parse HUNT_LOG.md for tested edges."""
    hunt_path = os.path.join(REPO, "HUNT_LOG.md")
    if not os.path.exists(hunt_path):
        return []
    try:
        with open(hunt_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return []

    entries = []
    # Parse table rows: | when | edge | IS | OOS | ... | verdict | why |
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "verdict" in line.lower() or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if len(cells) >= 11:
            entries.append({
                "when": cells[0],
                "edge": cells[1],
                "is_sharpe": cells[2],
                "oos_sharpe": cells[3],
                "verdict": cells[10] if len(cells) > 10 else "",
            })
    return entries


def collect_changelog_recent(days=14):
    """Parse recent entries from AI_CHANGELOG.md."""
    if not os.path.exists(CHANGELOG):
        return []
    try:
        with open(CHANGELOG, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return []

    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if len(cells) >= 5:
            date_str = cells[0]
            # Parse date (handle formats like 2026-07-10, 2026-07-08/09, ≤2026-07-07)
            m = re.match(r"(\d{4}-\d{2}-\d{2})", date_str)
            if m and m.group(1) >= cutoff:
                entries.append({
                    "date": date_str,
                    "role": cells[1],
                    "change": cells[2][:80] + "..." if len(cells[2]) > 80 else cells[2],
                    "commits": cells[4] if len(cells) > 4 else "",
                })
    return entries


# ── Velocity calculation ───────────────────────────────────────────────

def compute_velocity(notes_list, days=30):
    """Count items created in the last N days."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    count = 0
    for item in notes_list:
        created = item.get("created", "")
        if created and created >= cutoff:
            count += 1
    return count


# ── Dashboard generation ───────────────────────────────────────────────

def generate_dashboard():
    """Generate the full dashboard markdown."""
    papers = collect_notes(PAPERS_DIR, "paper")
    ideas = collect_notes(IDEAS_DIR, "idea")
    queued = collect_notes(QUEUE_DIR, "queued")
    running = collect_notes(EXPERIMENTS_DIR, "running")
    archived = collect_notes(ARCHIVE_DIR, "archived")
    hunt_entries = collect_hunt_entries()
    recent_ai = collect_changelog_recent(14)

    # Split archived into validated/rejected
    validated = [a for a in archived if a["status"] == "validated"]
    rejected = [a for a in archived if a["status"] == "rejected"]

    # Hunt log stats
    hunt_pass = [h for h in hunt_entries if "PASS" in h.get("verdict", "")]
    hunt_fail = [h for h in hunt_entries if "FAIL" in h.get("verdict", "")]

    # Velocity (last 30 days)
    all_items = papers + ideas + queued + running + archived
    velocity_30d = compute_velocity(all_items, 30)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append(f"# Research Dashboard")
    lines.append(f"_Auto-generated {now}. Do not edit — regenerate with `python scripts/research/research_dashboard.py`._")
    lines.append("")

    # Summary metrics
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| Papers imported | {len(papers)} |")
    lines.append(f"| Ideas | {len(ideas)} |")
    lines.append(f"| Experiments queued | {len(queued)} |")
    lines.append(f"| Experiments running | {len(running)} |")
    lines.append(f"| Experiments validated | {len(validated)} |")
    lines.append(f"| Experiments rejected | {len(rejected)} |")
    lines.append(f"| Hunt log entries | {len(hunt_entries)} |")
    lines.append(f"| Hunt PASS | {len(hunt_pass)} |")
    lines.append(f"| Hunt FAIL | {len(hunt_fail)} |")
    lines.append(f"| Velocity (30d) | {velocity_30d} new items |")
    lines.append("")

    # Pipeline status
    lines.append("## Pipeline Status")
    lines.append("")
    lines.append("```")
    lines.append(f"  Papers ({len(papers)})")
    lines.append(f"    v")
    lines.append(f"  Ideas ({len(ideas)})")
    lines.append(f"    v")
    lines.append(f"  Queued ({len(queued)}) -> Running ({len(running)})")
    lines.append(f"    v                        v")
    lines.append(f"  Validated ({len(validated)})  <- Gauntlet ->  Rejected ({len(rejected)})")
    lines.append(f"    v")
    lines.append(f"  HUNT_LOG: {len(hunt_pass)} PASS / {len(hunt_fail)} FAIL")
    lines.append("```")
    lines.append("")

    # Queued ideas
    if queued:
        lines.append("## Queued Experiments")
        lines.append("")
        lines.append("| ID | Title | Status | Created |")
        lines.append("|---|---|---|---|")
        for item in queued:
            eid = item["fm"].get("id", "")
            lines.append(f"| {eid} | {item['title']} | {item['status']} | {item['created']} |")
        lines.append("")

    # Running experiments
    if running:
        lines.append("## Running Experiments")
        lines.append("")
        lines.append("| ID | Title | Status | Script |")
        lines.append("|---|---|---|---|")
        for item in running:
            eid = item["fm"].get("id", "")
            script = item["fm"].get("script", "") or "(not set)"
            lines.append(f"| {eid} | {item['title']} | {item['status']} | {script} |")
        lines.append("")

    # Ideas
    if ideas:
        lines.append("## Ideas")
        lines.append("")
        lines.append("| Title | Status | Created |")
        lines.append("|---|---|---|")
        for item in ideas:
            lines.append(f"| [{item['title']}]({item['rel_path']}) | {item['status']} | {item['created']} |")
        lines.append("")

    # Papers
    if papers:
        lines.append("## Imported Papers")
        lines.append("")
        lines.append("| Title | Authors | Year | Status |")
        lines.append("|---|---|---|---|")
        for item in papers:
            authors = item["fm"].get("authors", "")
            year = item["fm"].get("year", "")
            lines.append(f"| [{item['title']}]({item['rel_path']}) | {authors} | {year} | {item['status']} |")
        lines.append("")

    # Graveyard
    if rejected:
        lines.append("## Rejected (Graveyard)")
        lines.append("_The graveyard is memory. Do not re-test these._")
        lines.append("")
        lines.append("| ID | Title | Idea | Paper |")
        lines.append("|---|---|---|---|")
        for item in rejected:
            eid = item["fm"].get("id", "")
            idea = item["fm"].get("idea", "")
            paper = item["fm"].get("paper", "")
            lines.append(f"| {eid} | {item['title']} | {idea} | {paper} |")
        lines.append("")

    if hunt_fail:
        lines.append("### Hunt Log Failures")
        lines.append("")
        lines.append("| Edge | OOS Sharpe | Verdict |")
        lines.append("|---|---|---|")
        for h in hunt_fail[:20]:  # last 20
            lines.append(f"| {h['edge']} | {h['oos_sharpe']} | {h['verdict']} |")
        if len(hunt_fail) > 20:
            lines.append(f"_...and {len(hunt_fail) - 20} more in HUNT_LOG.md_")
        lines.append("")

    # Validated
    if validated:
        lines.append("## Validated")
        lines.append("")
        lines.append("| ID | Title | Reviewer |")
        lines.append("|---|---|---|")
        for item in validated:
            eid = item["fm"].get("id", "")
            reviewer = item["fm"].get("reviewer", "")
            lines.append(f"| {eid} | {item['title']} | {reviewer} |")
        lines.append("")

    # Recent AI work
    if recent_ai:
        lines.append("## Recent AI Work (14 days)")
        lines.append("")
        lines.append("| Date | Role | Change | Commits |")
        lines.append("|---|---|---|---|")
        for entry in recent_ai[:20]:
            lines.append(f"| {entry['date']} | {entry['role']} | {entry['change']} | {entry['commits']} |")
        lines.append("")

    # Pass rate
    total_tested = len(validated) + len(rejected) + len(hunt_entries)
    if total_tested > 0:
        total_pass = len(validated) + len(hunt_pass)
        pass_rate = (total_pass / total_tested) * 100
        lines.append("## Research Statistics")
        lines.append("")
        lines.append(f"- **Total edges tested:** {total_tested}")
        lines.append(f"- **Pass rate:** {pass_rate:.1f}%")
        lines.append(f"- **Rejection rate:** {100 - pass_rate:.1f}%")
        lines.append(f"- _History: ~30 ideas in, ~2 survived long-term (the pipeline's job is to say no)_")
        lines.append("")

    lines.append("---")
    lines.append("_Back: [[Research Index]] | [[00 Dashboard]]_")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a research pipeline dashboard."
    )
    parser.add_argument("--print", action="store_true", help="Print to stdout instead of file")
    parser.add_argument("--dry-run", action="store_true", help="Summary only, no output file")
    parser.add_argument("--vault", action="store_true", help="Also write to vault/02-Strategy-Research/")
    args = parser.parse_args()

    papers = collect_notes(PAPERS_DIR, "paper")
    ideas = collect_notes(IDEAS_DIR, "idea")
    queued = collect_notes(QUEUE_DIR, "queued")
    running = collect_notes(EXPERIMENTS_DIR, "running")
    archived = collect_notes(ARCHIVE_DIR, "archived")

    if args.dry_run:
        print(f"[dry-run] papers={len(papers)} ideas={len(ideas)} queued={len(queued)} "
              f"running={len(running)} archived={len(archived)}")
        return

    content = generate_dashboard()

    if args.print:
        print(content)
        return

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = DASHBOARD_OUTPUT
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[dashboard] written: {os.path.relpath(out_path, REPO)}")

    if args.vault:
        os.makedirs(os.path.dirname(VAULT_DASHBOARD), exist_ok=True)
        if not os.path.exists(VAULT_DASHBOARD):
            with open(VAULT_DASHBOARD, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[vault] created: {os.path.relpath(VAULT_DASHBOARD, REPO)}")
        else:
            # Update only if content changed (replace file — it's auto-generated)
            with open(VAULT_DASHBOARD, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[vault] updated: {os.path.relpath(VAULT_DASHBOARD, REPO)}")


if __name__ == "__main__":
    main()
