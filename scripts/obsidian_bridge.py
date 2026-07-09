#!/usr/bin/env python3
"""
Obsidian Bridge — git-to-changelog-to-vault synchronizer.

Does three jobs (run individually or together via --all):
  1. changelog  — append new rows to docs/AI_CHANGELOG.md from git log
  2. state      — refresh the "Recent commits" block + timestamp in
                  docs/CURRENT_PROJECT_STATE.md
  3. vault      — generate/update Obsidian-friendly markdown in vault/

Never touches trading code. Only reads git metadata and writes docs/vault.

Usage:
  python scripts/obsidian_bridge.py --all
  python scripts/obsidian_bridge.py --changelog
  python scripts/obsidian_bridge.py --state
  python scripts/obsidian_bridge.py --vault
  python scripts/obsidian_bridge.py --post-commit   # auto: all, minus vault journal stub

Designed to be called from a git post-commit hook.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGELOG_PATH = os.path.join(REPO_ROOT, "docs", "AI_CHANGELOG.md")
STATE_PATH = os.path.join(REPO_ROOT, "docs", "CURRENT_PROJECT_STATE.md")
VAULT_DIR = os.path.join(REPO_ROOT, "vault")
JOURNAL_DIR = os.path.join(VAULT_DIR, "11-Daily-Journal")

# How many recent commits to show in CURRENT_PROJECT_STATE.md
STATE_COMMIT_COUNT = 8


# ── helpers ──────────────────────────────────────────────────────────────

def run_git(args, cwd=REPO_ROOT):
    """Run a git command, return stripped stdout string."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )
    return result.stdout.strip()


def git_log_entries(count=20):
    """Return list of dicts: hash, short_hash, date (YYYY-MM-DD), subject."""
    fmt = "%H|%h|%ai|%s"
    raw = run_git(["log", f"--format={fmt}", f"-{count}"])
    entries = []
    for line in raw.splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        full_hash, short_hash, iso_date, subject = parts
        # iso_date looks like "2026-07-10 01:31:07 +0200"
        date_str = iso_date.split(" ")[0]  # YYYY-MM-DD
        entries.append(
            {
                "hash": full_hash,
                "short": short_hash,
                "date": date_str,
                "subject": subject,
            }
        )
    return entries


def today_str():
    return datetime.date.today().isoformat()


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── 1. Changelog sync ───────────────────────────────────────────────────

CHANGELOG_TABLE_HEADER = "| Date | Role / model | Change | Evidence / verification | Commits |"
CHANGELOG_COL_COUNT = 5


def parse_changelog_commits(content):
    """Return set of short hashes already present in the changelog table."""
    seen = set()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.split("|")]
            # cells[0] is empty (leading |), cells[-1] is empty (trailing |)
            cells = [c for c in cells if c != ""]
            if len(cells) >= CHANGELOG_COL_COUNT:
                commits_cell = cells[4]
                # Extract short hashes (7-char hex or "(this commit)" etc.)
                for token in re.findall(r"\b[0-9a-f]{7,}\b", commits_cell):
                    seen.add(token[:7])
    return seen


def changelog_sync(entries, role="Obsidian Bridge / automated", evidence="git post-commit hook"):
    """
    Append new changelog rows for commits not yet recorded.
    Returns (n_added, list_of_new_entries).
    """
    if not os.path.exists(CHANGELOG_PATH):
        print(f"[changelog] {CHANGELOG_PATH} not found — skipping.")
        return 0, []

    content = read_file(CHANGELOG_PATH)
    seen = parse_changelog_commits(content)

    new_entries = []
    for e in reversed(entries):  # oldest first for append order
        if e["short"] in seen:
            continue
        # Skip the commit that created the changelog itself (seed)
        new_entries.append(e)

    if not new_entries:
        print("[changelog] already up to date.")
        return 0, []

    # Build new rows — insert before the last-row boundary (append to table end)
    rows = []
    for e in new_entries:
        subject = e["subject"]
        # Truncate very long subjects
        if len(subject) > 80:
            subject = subject[:77] + "..."
        row = f"| {e['date']} | {role} | {subject} | {evidence} | {e['short']} |"
        rows.append(row)

    # Append rows right after the last table row
    lines = content.splitlines()
    # Find the last line that starts with "|"
    last_table_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and not line.strip().startswith("|---"):
            # Make sure it's a data row, not separator
            if "---" not in line:
                last_table_idx = i

    if last_table_idx >= 0:
        insert_at = last_table_idx + 1
    else:
        # No table found — append at end
        insert_at = len(lines)

    for row in reversed(rows):
        lines.insert(insert_at, row)

    new_content = "\n".join(lines)
    if not new_content.endswith("\n"):
        new_content += "\n"

    write_file(CHANGELOG_PATH, new_content)
    print(f"[changelog] added {len(new_entries)} row(s).")
    return len(new_entries), new_entries


# ── 2. State doc sync ───────────────────────────────────────────────────

STATE_COMMIT_BLOCK_START = "```"
STATE_COMMIT_BLOCK_MARKER = "# Recent commits"  # not used directly; we find the code fence


def state_sync(entries):
    """
    Update the 'Recent commits' code block in CURRENT_PROJECT_STATE.md
    and bump the date in the header line.
    """
    if not os.path.exists(STATE_PATH):
        print(f"[state] {STATE_PATH} not found — skipping.")
        return

    content = read_file(STATE_PATH)
    lines = content.splitlines()

    # Find the "Recent commits" heading
    commit_header_idx = -1
    for i, line in enumerate(lines):
        if "Recent commits" in line and line.strip().startswith("#"):
            commit_header_idx = i
            break

    if commit_header_idx == -1:
        print("[state] could not find 'Recent commits' section — skipping commit refresh.")
    else:
        # Find the code fence after the header
        fence_start = -1
        fence_end = -1
        for i in range(commit_header_idx + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("```"):
                if fence_start == -1:
                    fence_start = i
                else:
                    fence_end = i
                    break

        if fence_start >= 0 and fence_end >= 0:
            # Build new commit block
            commit_lines = []
            for e in entries[:STATE_COMMIT_COUNT]:
                commit_lines.append(f"{e['short']}  {e['subject']}")
            new_block = (
                ["```"]
                + commit_lines
                + ["```"]
            )
            lines = lines[:fence_start] + new_block + lines[fence_end + 1:]
        else:
            print("[state] could not find code fence around commits — skipping.")

    # Update the header date line: "_Onboarding snapshot ..._"
    # or the first "# CURRENT PROJECT STATE — YYYY-MM-DD" line
    today = today_str()
    for i, line in enumerate(lines):
        if line.startswith("# CURRENT PROJECT STATE"):
            lines[i] = f"# CURRENT PROJECT STATE — {today}"
            break

    new_content = "\n".join(lines)
    if not new_content.endswith("\n"):
        new_content += "\n"

    write_file(STATE_PATH, new_content)
    print(f"[state] refreshed commits block + date ({today}).")


# ── 3. Vault sync ───────────────────────────────────────────────────────


def vault_sync(entries, new_changelog_entries=None):
    """
    Generate/update Obsidian vault content:
    - Daily journal stub for today (if missing)
    - Update dashboard freshness marker
    """
    today = today_str()
    n_updated = 0

    # --- Daily journal stub ---
    journal_path = os.path.join(JOURNAL_DIR, f"{today}.md")

    # Collect today's commits
    today_commits = [e for e in entries if e["date"] == today]

    if not os.path.exists(journal_path) and today_commits:
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        bullet_lines = []
        for e in today_commits:
            subject = e["subject"]
            if len(subject) > 100:
                subject = subject[:97] + "..."
            bullet_lines.append(f"- {subject} (`{e['short']}`)")

        stub = f"""---
type: journal
date: {today}
summary: {today_commits[0]['subject'] if today_commits else 'Automated entry'}
tags: [journal]
---
# {today}

**Commits today ({len(today_commits)}):**

{chr(10).join(bullet_lines)}

_Back: [[11-Daily-Journal/_index|Daily Journal]]_
"""
        write_file(journal_path, stub)
        print(f"[vault] created daily journal stub: {journal_path}")
        n_updated += 1
    elif os.path.exists(journal_path):
        # Update existing journal with any missing commits
        existing = read_file(journal_path)
        new_bullets = []
        for e in today_commits:
            if e["short"] not in existing:
                subject = e["subject"]
                if len(subject) > 100:
                    subject = subject[:97] + "..."
                new_bullets.append(f"- {subject} (`{e['short']}`)")
        if new_bullets:
            # Append before the back-link
            insertion = "\n".join(new_bullets)
            existing = existing.replace(
                "\n_Back:", f"\n{insertion}\n_Back:"
            )
            write_file(journal_path, existing)
            print(f"[vault] updated daily journal with {len(new_bullets)} new commit(s).")
            n_updated += 1
        else:
            print("[vault] daily journal already current.")
    else:
        print("[vault] no commits today — skipping journal stub.")

    # --- Dashboard freshness ---
    dashboard_path = os.path.join(VAULT_DIR, "00 Dashboard.md")
    if os.path.exists(dashboard_path):
        dash = read_file(dashboard_path)
        # Update or insert a freshness line
        freshness_line = f"> Last bridge sync: {today}"
        if "Last bridge sync:" in dash:
            dash = re.sub(
                r"> Last bridge sync: \d{4}-\d{2}-\d{2}",
                freshness_line,
                dash,
            )
        else:
            # Insert after the first blockquote line
            dash = re.sub(
                r"(^> \[!info\].*\n)",
                r"\1" + freshness_line + "\n",
                dash,
                count=1,
            )
        write_file(dashboard_path, dash)
        print(f"[vault] dashboard freshness updated ({today}).")
        n_updated += 1

    # --- Changelog mirror in vault ---
    vault_changelog_path = os.path.join(VAULT_DIR, "AI-ChangeLog.md")
    if os.path.exists(CHANGELOG_PATH):
        cl = read_file(CHANGELOG_PATH)
        # Add vault frontmatter + obsidian-style links
        vault_cl = f"""---
type: changelog
tags: [changelog, meta]
---
# AI Change Log

_Mirrored from `docs/AI_CHANGELOG.md` by obsidian_bridge.py._

"""
        # Strip the original H1 (first line starting with "# ")
        cl_body = re.sub(r"^# .+\n+", "", cl, count=1)
        vault_cl += cl_body
        write_file(vault_changelog_path, vault_cl)
        print(f"[vault] changelog mirror updated.")
        n_updated += 1

    if n_updated == 0:
        print("[vault] nothing to update.")
    return n_updated


# ── Main ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Obsidian Bridge — sync git → changelog → vault."
    )
    parser.add_argument(
        "--all", action="store_true", help="Run changelog + state + vault sync."
    )
    parser.add_argument(
        "--changelog", action="store_true", help="Append new commits to AI_CHANGELOG.md."
    )
    parser.add_argument(
        "--state", action="store_true", help="Refresh CURRENT_PROJECT_STATE.md."
    )
    parser.add_argument(
        "--vault", action="store_true", help="Generate/update Obsidian vault content."
    )
    parser.add_argument(
        "--post-commit",
        action="store_true",
        help="Post-commit mode: run --all + auto-commit changes with [bridge-auto] tag.",
    )
    parser.add_argument(
        "--role",
        default="Obsidian Bridge / automated",
        help="Role/model string for changelog rows.",
    )
    args = parser.parse_args()

    if args.post_commit:
        args.all = True

    if not (args.all or args.changelog or args.state or args.vault):
        parser.print_help()
        sys.exit(1)

    # Fetch git log once
    entries = git_log_entries(30)

    if args.all or args.changelog:
        n, new_entries = changelog_sync(entries, role=args.role)
    else:
        new_entries = []

    if args.all or args.state:
        state_sync(entries)

    if args.all or args.vault:
        vault_sync(entries, new_entries)

    # In post-commit mode, auto-commit the sync changes with the loop-breaker tag
    if args.post_commit:
        status = run_git(["status", "--porcelain"])
        if status:
            run_git(["add", "docs/AI_CHANGELOG.md", "docs/CURRENT_PROJECT_STATE.md",
                     "vault/"])
            run_git(["commit", "-m",
                     "Obsidian bridge auto-sync [bridge-auto]"])
            print("[obsidian-bridge] auto-committed sync changes.")
        else:            print("[obsidian-bridge] nothing to commit.")

    print("[obsidian-bridge] done.")


if __name__ == "__main__":
    main()
