"""agentctl — the enforcement point of the agent bridge.

    agentctl board                      status of every task
    agentctl claim  TASK-0001 --agent cline
    agentctl verify TASK-0001           THE GATE: whole-worktree diff vs contract
    agentctl result TASK-0001 --status COMPLETE --tests-passed 31
    agentctl review TASK-0001 --agent qwen --verdict APPROVED
    agentctl approve TASK-0001          human only; re-checks the commit hash

WHY THIS EXISTS
  Not to remind agents of the rules. To make their compliance irrelevant. Every decision here
  is computed from Git, never read from what an agent says it did. An implementer that edits a
  forbidden file and reports a clean file list fails verification on the Git evidence alone.

WHAT IT CANNOT DO
  Place an order, reach MT5, read credentials, or touch data/. It shells out to `git` and
  nothing else. The machine it runs on has no broker session -- that, not this file, is the
  reason an agent cannot trade.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AG = ROOT / ".agents"
WORKTREE_BASE = Path.home() / "desk-work"

# HARDCODED. Not read from the task, so a task cannot widen what counts as "not my work".
# These are the only paths a worktree may contain that are neither implementation nor a
# violation -- and only while they hash-match the copies made at claim time.
CONTROL_PATHS = (".agent-task/task.json", ".agent-task/policy.json",
                 ".agent-task/README.md", ".clinerules")


# ==================================================================== git
def git(*args, cwd=None, check=False):
    r = subprocess.run(["git", *args], cwd=str(cwd or ROOT),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.returncode, r.stdout, r.stderr


def _lines(out):
    return {l.strip() for l in out.splitlines() if l.strip()}


def sha256(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ==================================================================== control package
def materialize_control(wt: Path, task: dict, policy: dict, clinerules: str) -> dict:
    """Copy the briefing into the worktree and pin it by hash.

    A git worktree is a checkout of a COMMIT, so uncommitted bridge files cannot appear in it.
    That is why the first prototype failed: the implementer could not read its own contract.
    Copying solves it WITHOUT committing agent infrastructure to the deployment branch.

    These are copies, never the authority. verify() reads the contract from the main repo, so
    editing the copy changes nothing about what the work is judged against -- it only gets
    detected.
    """
    d = wt / ".agent-task"
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.json").write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    (d / "policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    (d / "README.md").write_text(
        f"# {task['task_id']}\n\n"
        f"{task['objective']}\n\n"
        f"## You may edit\n" + "\n".join(f"- `{p}`" for p in task["allowed_paths"]) +
        f"\n\n## You may never touch\n" +
        "\n".join(f"- `{p}`" for p in task["forbidden_paths"]) +
        "\n\nIn ANY form: committed, staged, unstaged, or as a new untracked file.\n"
        "`agentctl verify` scans the whole worktree, not just your commits.\n\n"
        "## Required tests\n" +
        "\n".join(f"- `{t}`" for t in task.get("required_tests", [])) +
        "\n\n## This directory is not yours\n"
        "`.agent-task/` and `.clinerules` are pinned by SHA-256 at claim time. Modifying,\n"
        "deleting or committing any of them fails verification as CONTROL_TAMPERED.\n"
        "The authoritative contract lives in the main repository and governs regardless.\n",
        encoding="utf-8")
    if clinerules is not None:
        (wt / ".clinerules").write_text(clinerules, encoding="utf-8")

    hashes = {}
    for rel in CONTROL_PATHS:
        f = wt / rel
        if f.exists():
            hashes[rel] = sha256(f)
            try:
                f.chmod(0o444)      # a speed bump that signals intent. The hash is the control.
            except Exception:
                pass
    return hashes


def check_control(wt: Path, hashes: dict, committed: set) -> list:
    """Missing, modified or COMMITTED control files are all tampering.

    Deletion is treated exactly like modification: an implementer that removes its contract
    has changed what it is working from just as surely as one that edits it.
    """
    v = []
    for rel, want in (hashes or {}).items():
        f = wt / rel
        if not f.exists():
            v.append({"path": rel, "rule": "CONTROL_TAMPERED", "detail": "control file DELETED"})
            continue
        got = sha256(f)
        if got != want:
            v.append({"path": rel, "rule": "CONTROL_TAMPERED",
                      "detail": f"modified (sha {got[:12]} != {want[:12]})"})
        if rel in committed:
            v.append({"path": rel, "rule": "CONTROL_COMMITTED",
                      "detail": "control metadata committed to the task branch"})
    return v


def worktree_paths(wt: Path, base_commit: str, forbidden: list) -> dict:
    """EVERY path the worktree touches, by category.

    Validating only `base..HEAD` would let an agent leave a forbidden edit uncommitted and
    pass. The union below is the actual state of the tree, which is what a human would see
    and what a later commit would capture.

    --no-renames matters: with rename detection a moved file reports only its new path, so a
    file renamed OUT of a forbidden directory would hide the original. Split into delete+add
    and both sides are checked.
    """
    out = {}
    _, committed, _ = git("diff", "--name-only", "--no-renames",
                          f"{base_commit}..HEAD", cwd=wt)
    out["committed"] = _lines(committed)
    _, staged, _ = git("diff", "--name-only", "--no-renames", "--cached", cwd=wt)
    out["staged"] = _lines(staged)
    _, unstaged, _ = git("diff", "--name-only", "--no-renames", cwd=wt)
    out["unstaged"] = _lines(unstaged)
    _, untracked, _ = git("ls-files", "--others", "--exclude-standard", cwd=wt)
    out["untracked"] = _lines(untracked)

    # Gitignored files are invisible to the scan above. A forbidden directory that is ALSO
    # gitignored (data/ is) could therefore hide a new file, so those are queried explicitly.
    ignored = set()
    dirs = [p[:-3] for p in forbidden if p.endswith("/**")]
    if dirs:
        _, ig, _ = git("ls-files", "--others", "--ignored", "--exclude-standard",
                       "--", *dirs, cwd=wt)
        ignored = _lines(ig)
    out["untracked_ignored"] = ignored
    out["all"] = set().union(*out.values())
    return out


# ==================================================================== matching
def match(path: str, pattern: str) -> bool:
    """`dir/**` is a prefix match; anything else is fnmatch.

    fnmatch alone is too loose here -- its `*` crosses `/`, so `config/**` would also match
    `configuration.py`. Path rules that quietly over- or under-match are worse than none.
    """
    if pattern.endswith("/**"):
        d = pattern[:-3]
        return path == d or path.startswith(d + "/")
    return fnmatch.fnmatch(path, pattern)


def validate(paths: set, task: dict) -> list:
    """Every violation, not just the first -- a partial report invites a second round trip."""
    v = []
    allowed = task.get("allowed_paths") or []
    forbidden = task.get("forbidden_paths") or []
    for p in sorted(paths):
        if any(match(p, f) for f in forbidden):
            v.append({"path": p, "rule": "FORBIDDEN",
                      "detail": next(f for f in forbidden if match(p, f))})
        elif allowed and not any(match(p, a) for a in allowed):
            v.append({"path": p, "rule": "NOT_ALLOWED",
                      "detail": f"outside allowed_paths {allowed}"})
    return v


# ==================================================================== review package
def review_schema(task_id: str, head: str) -> str:
    """Built, not .format()-ed. A JSON template is mostly literal braces, so string
    formatting fights the content it is trying to emit -- the first attempt raised
    KeyError on `{"severity"`. Concatenation has no such failure mode."""
    return (
        '{\n'
        f'  "task_id": "{task_id}",\n'
        f'  "reviewed_commit": "{head}",\n'
        '  "verdict": "APPROVED | REJECTED | CHANGES_REQUESTED",\n'
        '  "findings": [],\n'
        '  "required_followup": []\n'
        '}'
    )

# The ONLY fields copied out of model output. Anything else it returns is discarded, so a
# reviewer cannot smuggle in a status change, a path grant, or a new hash by adding keys.
REVIEW_ALLOWED_FIELDS = ("task_id", "reviewed_commit", "verdict", "findings",
                         "required_followup", "summary")
VERDICTS = ("APPROVED", "REJECTED", "CHANGES_REQUESTED")


def build_review_package(task: dict, diff: str, head: str, test_cmd: str,
                         test_rc: int, test_tail: str) -> str:
    """Everything the reviewer needs and nothing else.

    No chat history, no repository dump, no credentials, no trading evidence. A reviewer that
    receives the whole conversation inherits its assumptions -- the point of an independent
    review is that it sees only the artefact.
    """
    return f"""You are an INDEPENDENT CODE REVIEWER. You are read-only: you cannot edit,
commit, or run anything. Your only output is one JSON object.

## Task objective
{task['objective']}

## Acceptance criteria
""" + "\n".join(f"- {c}" for c in task.get("acceptance_criteria", [])) + f"""

## Paths the implementer was allowed to change
{task['allowed_paths']}

## Paths the implementer was forbidden to change
{task['forbidden_paths']}

## Commits
base_commit     {task['base_commit']}
reviewed_commit {head}

## Exact git diff (base..reviewed)
```diff
{diff}
```

## Test evidence, observed independently by the harness (not reported by the implementer)
command   {test_cmd}
exit_code {test_rc}
output    {test_tail}

## Your job
Judge ONLY whether the diff satisfies the acceptance criteria and stays within the allowed
paths. Do not propose refactors. Do not comment on style. If the diff is correct and in
scope, APPROVE it -- an unnecessary rejection costs a round trip.

Reply with ONE JSON object and nothing else. Use these EXACT literal values for the first
two fields -- do not substitute, abbreviate, or describe them:
{review_schema(task['task_id'], head)}
"""


def model_text(stdout: str):
    """Unwrap the openclaw --json envelope.

    Plain stdout is prefixed with four human-readable metadata lines ("model.run via local",
    "provider:", ...), so it is never bare JSON -- the first review attempt failed on that,
    and the failure looked like a bad model when the model had answered correctly. --json
    returns a structured envelope instead, and the reply is outputs[0].text.
    """
    try:
        env = json.loads(stdout)
    except Exception as e:
        return None, f"openclaw --json output unparseable: {e}"
    outs = env.get("outputs") or []
    if not outs or not isinstance(outs, list):
        return None, f"envelope has no outputs (ok={env.get('ok')})"
    return (outs[0] or {}).get("text"), None


def parse_review(raw: str, task_id: str, expected_commit: str):
    """Validate model output. FAIL CLOSED -- any doubt produces no review at all.

    A model is an untrusted input source like any other. It can return prose, truncated JSON,
    a different task's id, or extra fields hoping something downstream reads them. None of
    that may become an accepted review.
    """
    txt = (raw or "").strip()
    obj = None
    try:
        obj = json.loads(txt)
    except Exception:
        # tolerate a fenced block, but nothing looser -- no regex scraping of prose
        if "```" in txt:
            for part in txt.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    try:
                        obj = json.loads(part)
                        break
                    except Exception:
                        continue
    if obj is None:
        return None, "model output is not valid JSON"
    if not isinstance(obj, dict):
        return None, f"expected a JSON object, got {type(obj).__name__}"
    if obj.get("task_id") != task_id:
        return None, f"task_id mismatch: {obj.get('task_id')!r} != {task_id!r}"
    if obj.get("reviewed_commit") != expected_commit:
        return None, (f"reviewed_commit mismatch: {obj.get('reviewed_commit')!r} != "
                      f"{expected_commit!r}")
    if obj.get("verdict") not in VERDICTS:
        return None, f"verdict {obj.get('verdict')!r} not in {VERDICTS}"
    if not isinstance(obj.get("findings"), list):
        return None, "findings must be a list"
    clean = {k: v for k, v in obj.items() if k in REVIEW_ALLOWED_FIELDS}
    dropped = sorted(set(obj) - set(clean))
    if dropped:
        clean["_dropped_fields"] = dropped      # recorded, never acted on
    return clean, None


# ==================================================================== store
def _read(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def task_path(tid):    return AG / "tasks" / f"{tid}.json"
def result_path(tid):  return AG / "results" / f"{tid}.json"
def lock_path(tid):    return AG / "locks" / f"{tid}.lock"
def review_paths(tid): return sorted((AG / "reviews").glob(f"{tid}.*.json"))


def audit(tid, action, **fields):
    p = AG / "audit" / f"{datetime.now(timezone.utc).date()}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "task_id": tid, "action": action, **fields}) + "\n")


def set_status(tid, status, **extra):
    t = _read(task_path(tid))
    t["status"] = status
    t.update(extra)
    _write(task_path(tid), t)
    audit(tid, "STATUS", status=status)


# ==================================================================== commands
def cmd_claim(a):
    t = _read(task_path(a.task_id))
    if t is None:
        sys.exit(f"no such task {a.task_id}")
    lk = _read(lock_path(a.task_id))
    if lk:
        exp = datetime.fromisoformat(lk["lease_expires_utc"])
        if exp > datetime.now(timezone.utc):
            sys.exit(f"held by {lk['agent']} until {exp:%H:%M:%S} UTC")
        print(f"  lease expired at {exp:%H:%M:%S} UTC -- reclaiming")

    wt = WORKTREE_BASE / a.task_id
    branch = f"task/{a.task_id.split('-')[-1]}"
    if not wt.exists():
        WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
        rc, _, err = git("worktree", "add", str(wt), "-b", branch, t["base_commit"])
        if rc != 0:
            sys.exit(f"worktree failed: {err.strip()}")
    policy = _read(AG / "policy.json") or {}
    cr = (ROOT / ".clinerules")
    hashes = materialize_control(wt, t, policy,
                                 cr.read_text(encoding="utf-8") if cr.exists() else None)

    _write(lock_path(a.task_id), {
        "agent": a.agent, "worktree": str(wt), "branch": branch,
        "control_hashes": hashes,
        "claimed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lease_expires_utc": (datetime.now(timezone.utc)
                              + timedelta(minutes=t.get("lease_minutes", 60))
                              ).isoformat(timespec="seconds")})
    set_status(a.task_id, "CLAIMED", claimed_by=a.agent)
    print(f"CLAIMED {a.task_id} by {a.agent}")
    print(f"  branch   {branch}   base {t['base_commit'][:8]}")
    print(f"  allowed  {t['allowed_paths']}")
    print(f"  control  {len(hashes)} files pinned by sha256")
    print()
    print(f"  OPEN THIS EXACT FOLDER IN VS CODE:")
    print(f"      {wt}")
    print(f"  Not {wt.parent} -- Cline reads .clinerules from the WORKSPACE ROOT,")
    print(f"  so opening the parent means it finds no rules and no contract.")


def verifier_provenance() -> dict:
    """WHO verified, provably.

    A task that modifies agentctl.py must not become its own verification authority. This
    records the identity of the running verifier so the audit can show it was the control
    copy and not the implementation under review. sha256 of the file bytes is the primary
    identity because it is exact even when the verifier is uncommitted.
    """
    me = Path(__file__).resolve()
    rc, out, _ = git("log", "-1", "--format=%H", "--", "scripts/agentctl.py")
    return {"verifier_path": str(me), "verifier_sha256": sha256(me),
            "verifier_last_commit": out.strip() or None}


def cmd_verify(a):
    t, lk = _read(task_path(a.task_id)), _read(lock_path(a.task_id))
    if not t or not lk:
        sys.exit("task or lock missing -- claim it first")
    wt = Path(lk["worktree"])
    if not wt.exists():
        sys.exit(f"worktree gone: {wt}")

    p = worktree_paths(wt, t["base_commit"], t.get("forbidden_paths") or [])

    # Control metadata is scaffolding, not work -- but ONLY while it is intact. Tampered or
    # committed control files are violations, and are never excluded from scrutiny.
    control_v = check_control(wt, lk.get("control_hashes"), p["committed"])
    tampered = {c["path"] for c in control_v}
    impl = {x for x in p["all"] if x not in CONTROL_PATHS or x in tampered}
    violations = control_v + validate(impl, t)

    prov = verifier_provenance()
    _, impl_head, _ = git("rev-parse", "HEAD", cwd=wt)
    print(f"VERIFY {a.task_id}")
    print(f"  verifier {prov['verifier_path']}")
    print(f"           sha256 {prov['verifier_sha256'][:16]}  "
          f"last commit {(prov['verifier_last_commit'] or 'uncommitted')[:8]}")
    print(f"  reviewing implementation {impl_head.strip()[:8]}")
    if prov["verifier_path"].startswith(str(wt)):
        sys.exit("REFUSED: the verifier lives inside the implementation worktree. "
                 "A change under review must not verify itself.")
    print(f"  control  {len(lk.get('control_hashes') or {})} pinned, "
          f"{'INTACT' if not control_v else 'TAMPERED'}")
    for k in ("committed", "staged", "unstaged", "untracked", "untracked_ignored"):
        shown = sorted(x for x in p[k] if x not in CONTROL_PATHS or x in tampered)
        if shown:
            print(f"  {k:<18}{shown}")
    if not impl:
        print("  (no implementation changes yet)")

    # The agent's self-report is compared but never trusted for the decision.
    res = _read(result_path(a.task_id))
    if res:
        claimed = set(res.get("files_changed") or [])
        if claimed != impl:
            print(f"  !! result JSON claims {sorted(claimed)}")
            print(f"     git says          {sorted(impl)}")
            print(f"     -> recorded as a safety finding; decision uses GIT")

    if violations:
        print("\n  REJECTED_BY_POLICY:")
        for v in violations:
            print(f"    {v['path']}  [{v['rule']}] {v['detail']}")
        set_status(a.task_id, "REJECTED_BY_POLICY", violations=violations)
        audit(a.task_id, "VERIFY", ok=False, violations=violations, **prov)
        sys.exit(2)

    _, head, _ = git("rev-parse", "HEAD", cwd=wt)
    set_status(a.task_id, "VERIFIED", head_commit=head.strip())
    audit(a.task_id, "VERIFY", ok=True, head=head.strip(), paths=sorted(impl), **prov)
    print(f"\n  VERIFIED at {head.strip()[:8]} -- every path satisfies the contract")


def cmd_result(a):
    t, lk = _read(task_path(a.task_id)), _read(lock_path(a.task_id))
    wt = Path(lk["worktree"])
    p = worktree_paths(wt, t["base_commit"], t.get("forbidden_paths") or [])
    impl = {x for x in p["all"] if x not in CONTROL_PATHS}
    _, head, _ = git("rev-parse", "HEAD", cwd=wt)
    _write(result_path(a.task_id), {
        "task_id": a.task_id, "agent": lk["agent"], "model": a.model,
        "base_commit": t["base_commit"], "head_commit": head.strip(),
        "files_changed": sorted(impl),
        "tests_executed": t.get("required_tests", []),
        "test_results": {"passed": a.tests_passed, "failed": a.tests_failed},
        "uncertainties": a.uncertainty or [], "safety_findings": [],
        "completion_status": a.status})
    set_status(a.task_id, "IMPLEMENTED")
    print(f"result written for {a.task_id} ({a.status})")


def cmd_review(a):
    t = _read(task_path(a.task_id))
    if t.get("status") != "VERIFIED":
        sys.exit(f"cannot review: status is {t.get('status')}, expected VERIFIED")
    lk = _read(lock_path(a.task_id))
    wt = Path(lk["worktree"])
    _, head, _ = git("rev-parse", "HEAD", cwd=wt)
    head = head.strip()
    # A review must bind to a commit that CONTAINS the work. With the implementation still
    # untracked, HEAD is the base commit -- the review would look valid while binding to a
    # tree without the change, and no later edit would ever move the hash.
    if head == t["base_commit"]:
        sys.exit("cannot review: HEAD == base_commit, so nothing is committed. "
                 "A review would bind to a tree that does not contain the work. "
                 "Commit the implementation on the task branch first.")
    if a.via_model:
        _, diff, _ = git("diff", "--no-renames", f"{t['base_commit']}..HEAD", cwd=wt)
        cmd = t.get("required_tests", ["<none>"])[0]
        # the harness runs the test ITSELF -- the reviewer is told what was observed, never
        # what the implementer claimed
        tr = subprocess.run([sys.executable, cmd], cwd=str(wt),
                            capture_output=True, text=True)
        tail = (tr.stdout or tr.stderr or "").strip().splitlines()[-3:]
        pkg = build_review_package(t, diff, head, f"python3 {cmd}",
                                   tr.returncode, " | ".join(tail))
        print(f"  invoking {a.via_model} with a {len(pkg)} char package ...")
        r = subprocess.run(["openclaw", "infer", "model", "run", "--model", a.via_model,
                            "--prompt", pkg, "--json"],
                           capture_output=True, text=True, timeout=900)
        text, env_err = model_text(r.stdout)
        if text is None:
            audit(a.task_id, "REVIEW_REJECTED", model=a.via_model, error=env_err)
            sys.exit(f"MODEL ENVELOPE REJECTED: {env_err}\n  no review was written")
        review, err = parse_review(text, a.task_id, head)
        if review is None:
            audit(a.task_id, "REVIEW_REJECTED", model=a.via_model, error=err)
            sys.exit(f"MODEL OUTPUT REJECTED: {err}\n  no review was written (fail closed)")
        review.update({"reviewing_agent": a.agent, "model": a.via_model})
    else:
        review = {"task_id": a.task_id, "reviewed_commit": head,
                  "verdict": a.verdict, "reviewing_agent": a.agent, "model": a.model,
                  "findings": [{"severity": "INFO", "claim": f} for f in (a.finding or [])],
                  "required_followup": []}
    _write(AG / "reviews" / f"{a.task_id}.{a.agent}.json", review)
    set_status(a.task_id, "REVIEWED")
    print(f"review by {a.agent} ({review.get('model')}): "
          f"{review['verdict']} @ {head[:8]}, {len(review['findings'])} finding(s)")


def cmd_approve(a):
    t, lk = _read(task_path(a.task_id)), _read(lock_path(a.task_id))
    revs = review_paths(a.task_id)
    if not revs:
        sys.exit("no review exists")
    _, head, _ = git("rev-parse", "HEAD", cwd=Path(lk["worktree"]))
    head = head.strip()
    for rp in revs:
        r = _read(rp)
        if r["reviewed_commit"] != head:
            set_status(a.task_id, "IMPLEMENTED")
            sys.exit(f"REVIEW VOID: {rp.name} reviewed {r['reviewed_commit'][:8]} but HEAD is "
                     f"{head[:8]}. The code changed after review; re-verify and re-review.")
        if r["verdict"] != "APPROVED":
            sys.exit(f"{rp.name} verdict is {r['verdict']}")
    set_status(a.task_id, "HUMAN_APPROVED", approved_commit=head)
    audit(a.task_id, "APPROVE", head=head, by="human")
    print(f"HUMAN_APPROVED {a.task_id} @ {head[:8]}")
    print(f"  merge with:  git merge --no-ff {lk['branch']}")


def cmd_board(a):
    rows = []
    for tp in sorted((AG / "tasks").glob("*.json")):
        t = _read(tp)
        lk = _read(lock_path(t["task_id"]))
        rows.append((t["task_id"], t.get("status", "?"), t.get("risk_level", "?"),
                     (lk or {}).get("agent", "-"), t["objective"][:44]))
    if not rows:
        print("no tasks")
        return
    print(f"{'TASK':<12}{'STATUS':<20}{'RISK':<7}{'AGENT':<10}OBJECTIVE")
    for r in rows:
        print(f"{r[0]:<12}{r[1]:<20}{r[2]:<7}{r[3]:<10}{r[4]}")


def main():
    ap = argparse.ArgumentParser(prog="agentctl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("board")
    for name in ("claim", "verify", "approve"):
        s = sub.add_parser(name)
        s.add_argument("task_id")
        if name == "claim":
            s.add_argument("--agent", required=True)
    s = sub.add_parser("result")
    s.add_argument("task_id"); s.add_argument("--model", default="unknown")
    s.add_argument("--status", default="COMPLETE")
    s.add_argument("--tests-passed", type=int, default=0)
    s.add_argument("--tests-failed", type=int, default=0)
    s.add_argument("--uncertainty", action="append")
    s = sub.add_parser("review")
    s.add_argument("task_id"); s.add_argument("--agent", required=True)
    s.add_argument("--model", default="unknown")
    s.add_argument("--verdict", choices=list(VERDICTS),
                   help="manual verdict; omit when using --via-model")
    s.add_argument("--via-model", metavar="PROVIDER/MODEL",
                   help="invoke a read-only one-shot model, e.g. ollama/qwen2.5-coder:7b")
    s.add_argument("--finding", action="append")
    a = ap.parse_args()
    {"board": cmd_board, "claim": cmd_claim, "verify": cmd_verify, "result": cmd_result,
     "review": cmd_review, "approve": cmd_approve}[a.cmd](a)


if __name__ == "__main__":
    main()
