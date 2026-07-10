#!/usr/bin/env python3
"""
paper_index.py — Build a searchable index of research papers.

Scans all research/papers/*.md files, parses YAML frontmatter and body text,
and produces a structured index in JSON and/or Markdown format.

Never modifies paper notes. Never touches production code.
Research firewall respected.

Usage:
    python scripts/research/paper_index.py                   # writes json + markdown
    python scripts/research/paper_index.py --json             # json only
    python scripts/research/paper_index.py --markdown         # markdown only
    python scripts/research/paper_index.py --print            # print to stdout
    python scripts/research/paper_index.py --search "ORB"     # search and print
    python scripts/research/paper_index.py --dry-run          # parse + summary, no write
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PAPERS_DIR = REPO / "research" / "papers"
RESULTS_DIR = REPO / "research" / "results"


# ── YAML frontmatter parsing ────────────────────────────────────────────

def parse_frontmatter(text):
    """
    Parse YAML frontmatter (between --- markers) into a dict.
    Handles simple key: value and key: [item, item] syntax.
    Does NOT require PyYAML — keeps zero external deps.
    """
    fm = {}
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return fm

    block = match.group(1)
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # key: value  or  key: [a, b, c]  or  key: value  # comment
        m = re.match(r"^([\w-]+)\s*:\s*(.*)$", stripped)
        if not m:
            continue

        key = m.group(1).strip()
        val = m.group(2).strip()

        # Strip inline comments (but keep # inside quotes/brackets)
        if "#" in val and not val.startswith("[") and not val.startswith('"'):
            # Check # is not inside a quoted string
            if not (val.startswith("'") or val.startswith('"')):
                val = val.split("#")[0].strip()

        # Parse list values: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if inner:
                items = [item.strip().strip("\"'") for item in inner.split(",")]
                fm[key] = [item for item in items if item]
            else:
                fm[key] = []
        # Strip surrounding quotes
        elif val.startswith('"') and val.endswith('"'):
            fm[key] = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            fm[key] = val[1:-1]
        else:
            fm[key] = val

    return fm


# ── Body text extraction helpers ─────────────────────────────────────────

def extract_section(body, section_name):
    """Extract the text content under a ## section heading."""
    pattern = rf"^##\s+{re.escape(section_name)}\s*\n(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, body, re.DOTALL | re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def extract_field_from_body(body, label):
    """
    Extract a field from a 'Auto-Classification' style section.
    Looks for '**Label:** value' patterns.
    """
    pattern = rf"\*\*{re.escape(label)}:\*\*\s*(.+)"
    matches = re.findall(pattern, body)
    if matches:
        val = matches[0].strip()
        if val.lower() in ("unclearified", "unclassified", ""):
            return None
        return val
    return None


def extract_list_from_body(body, label):
    """Extract bullet-list items following a '**Label:**' heading."""
    pattern = rf"\*\*{re.escape(label)}[:\*]?\*\*\s*\n((?:-\s+.+\n?)+)"
    match = re.search(pattern, body)
    if not match:
        return []
    items = re.findall(r"^-\s+(.+)$", match.group(1), re.MULTILINE)
    return [item.strip() for item in items]


def parse_paper(filepath):
    """
    Parse a single paper .md file into a structured dict.
    Merges frontmatter data with body-extracted fallbacks.
    """
    text = filepath.read_text(encoding="utf-8")

    # Split frontmatter and body
    fm_match = re.match(r"^(---\s*\n.*?\n---)\s*\n(.*)", text, re.DOTALL)
    if fm_match:
        frontmatter = parse_frontmatter(text)
        body = fm_match.group(2)
    else:
        frontmatter = {}
        body = text

    auto_class = extract_section(body, "Auto-Classification")

    # Build the unified record
    record = {
        "filename": filepath.name,
        "filepath": str(filepath.relative_to(REPO)),
        "title": frontmatter.get("title", filepath.stem),
        "authors": _normalise_list(frontmatter.get("authors")),
        "year": _normalise_int(frontmatter.get("year")),
        "url": frontmatter.get("url", ""),
        "status": frontmatter.get("status", "unknown"),
        "strategy": _normalise_list(frontmatter.get("strategy_types")) or
                     _split_csv(extract_field_from_body(auto_class, "Strategy type")),
        "markets": _normalise_list(frontmatter.get("markets")) or
                   _split_csv(extract_field_from_body(auto_class, "Markets")),
        "timeframes": _normalise_list(frontmatter.get("timeframes")) or
                       _split_csv(extract_field_from_body(auto_class, "Timeframes")),
        "keywords": _normalise_list(frontmatter.get("tags")) or
                     _split_csv(extract_field_from_body(body, "Keywords")),
        "edge": extract_list_from_body(auto_class, "Edge / mechanism")
                 or extract_list_from_body(body, "Edge / mechanism"),
        "limitations": extract_list_from_body(auto_class, "Limitations detected")
                       or extract_list_from_body(body, "Limitations detected"),
        "related_experiments": _extract_related_experiments(body),
    }

    return record


def _normalise_list(val):
    """Normalise a frontmatter value into a list of strings."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    val = str(val).strip()
    if not val:
        return []
    return [val]


def _normalise_int(val):
    """Try to coerce val to int, return original string on failure."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return val


def _split_csv(val):
    """Split a comma-separated string into a list, handling None."""
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


def _extract_related_experiments(body):
    """Find references to experiment files or [[links]] in the body."""
    experiments = set()
    # [[WikiLinks]]
    for m in re.finditer(r"\[\[([^\]]+)\]\]", body):
        link = m.group(1).strip()
        # Filter out generic navigation links
        if link.lower() not in ("research index", "00 dashboard"):
            experiments.add(link)
    # Explicit experiment file references
    for m in re.finditer(r"research/experiments/([\w/-]+\.md)", body):
        experiments.add(m.group(1))
    return sorted(experiments)


# ── Index building ───────────────────────────────────────────────────────

def build_index(papers_dir=PAPERS_DIR):
    """Scan papers_dir for *.md files and build a sorted index."""
    papers = []
    if not papers_dir.exists():
        return papers

    for md_file in sorted(papers_dir.glob("*.md")):
        try:
            record = parse_paper(md_file)
            papers.append(record)
        except Exception as e:
            print(f"[warn] Failed to parse {md_file.name}: {e}", file=sys.stderr)

    return papers


# ── Output formatters ────────────────────────────────────────────────────

def to_json(papers):
    """Serialise papers list to a JSON string."""
    return json.dumps(papers, indent=2, ensure_ascii=False) + "\n"


def to_markdown(papers):
    """Format papers as a markdown table."""
    if not papers:
        return "_No papers indexed yet._\n"

    header = "| # | Title | Authors | Year | Strategy | Markets | Status |\n"
    separator = "|---|-------|---------|------|----------|---------|--------|\n"

    rows = []
    for i, p in enumerate(papers, 1):
        title = p["title"]
        authors = ", ".join(p["authors"]) if isinstance(p["authors"], list) else str(p["authors"])
        year = str(p["year"] or "")
        strategy = ", ".join(p["strategy"]) if p["strategy"] else "—"
        markets = ", ".join(p["markets"]) if p["markets"] else "—"
        status = p["status"]
        rows.append(f"| {i} | {title} | {authors} | {year} | {strategy} | {markets} | {status} |\n")

    return header + separator + "".join(rows)


def print_summary(papers):
    """Print a concise summary of the index."""
    print(f"Papers indexed: {len(papers)}")
    for p in papers:
        title = p["title"]
        status = p["status"]
        strategy = ", ".join(p["strategy"]) if p["strategy"] else "—"
        print(f"  • {title}  [{status}]  strategy: {strategy}")


def search_papers(papers, query):
    """
    Case-insensitive search across all text fields of each paper.
    Returns matching papers.
    """
    q_lower = query.lower()
    results = []
    for p in papers:
        # Build a single searchable blob from all fields
        blob_parts = []
        for v in p.values():
            if isinstance(v, list):
                blob_parts.extend(str(item) for item in v)
            elif v is not None:
                blob_parts.append(str(v))
        blob = " ".join(blob_parts).lower()
        if q_lower in blob:
            results.append(p)
    return results


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build a searchable index of research papers."
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json", action="store_true",
        help="Write research/results/paper_index.json"
    )
    output_group.add_argument(
        "--markdown", action="store_true",
        help="Write research/results/paper_index.md"
    )
    output_group.add_argument(
        "--print", action="store_true",
        help="Print the full index to stdout"
    )
    parser.add_argument(
        "--search", metavar="<query>",
        help="Search papers by keyword across all fields, print results"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and print summary without writing files"
    )

    args = parser.parse_args()

    # Build the index
    papers = build_index()

    # ── Search mode ──
    if args.search:
        results = search_papers(papers, args.search)
        print(f"Search: '{args.search}' — {len(results)} match(es)\n")
        for i, p in enumerate(results, 1):
            print(f"  [{i}] {p['title']}  ({p['filename']})")
            if p["strategy"]:
                print(f"      strategy: {', '.join(p['strategy'])}")
            if p["markets"]:
                print(f"      markets:  {', '.join(p['markets'])}")
            print(f"      status:   {p['status']}")
        return

    # ── Dry-run mode ──
    if args.dry_run:
        print("=== DRY RUN — no files written ===\n")
        print_summary(papers)
        return

    # ── Print mode ──
    if args.print:
        print(to_markdown(papers))
        return

    # ── File output modes ──
    write_json = args.json
    write_md = args.markdown

    # Default: both json + markdown
    if not write_json and not write_md:
        write_json = True
        write_md = True

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if write_json:
        json_path = RESULTS_DIR / "paper_index.json"
        json_path.write_text(to_json(papers), encoding="utf-8")
        print(f"Wrote {json_path.relative_to(REPO)}")

    if write_md:
        md_path = RESULTS_DIR / "paper_index.md"
        md_path.write_text(to_markdown(papers), encoding="utf-8")
        print(f"Wrote {md_path.relative_to(REPO)}")

    print_summary(papers)


if __name__ == "__main__":
    main()
