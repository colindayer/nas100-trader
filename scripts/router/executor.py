"""executor.py -- automatic task execution for the AI Task Router.

When the router dispatches a task whose `inputs` names a known ACTION, the
executor runs the mapped EXISTING script (nothing new is built here), captures
stdout/stderr/exit-code/duration, appends an execution log to the task body,
flips the status automatically (completed on exit 0, review on failure), and
queues the follow-up task in the chain when appropriate.

Task convention:  inputs: "<action>: <cli arguments>"     (arguments optional)
    e.g.          inputs: "import_paper: 'Moskowitz TSMOM' --year 2012"

Actions (all map to scripts that already exist):
    import_paper        -> scripts/research/new_paper.py
    create_idea         -> scripts/research/new_idea.py
    create_experiment   -> scripts/research/new_experiment.py
    run_experiment      -> scripts/research/run_experiment.py
    update_paper_index  -> scripts/research/paper_index.py
    update_dashboard    -> scripts/research/research_dashboard.py
    update_obsidian     -> scripts/obsidian/build_obsidian.py

Follow-up chain (queued automatically, deduplicated):
    import_paper -> update_paper_index -> update_obsidian
    run_experiment -> update_dashboard -> update_obsidian

Guardrails: only whitelisted scripts run (never arbitrary commands, never
production code); timeout 300s; follow-ups are skipped if an equivalent
non-terminal task already exists (idempotent chains).
"""
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import TERMINAL          # noqa: E402
import queue as q                    # noqa: E402

REPO = q.REPO
PY = sys.executable

ACTIONS = {
    "import_paper":       "scripts/research/new_paper.py",
    "create_idea":        "scripts/research/new_idea.py",
    "create_experiment":  "scripts/research/new_experiment.py",
    "run_experiment":     "scripts/research/run_experiment.py",
    "update_paper_index": "scripts/research/paper_index.py",
    "update_dashboard":   "scripts/research/research_dashboard.py",
    "update_obsidian":    "scripts/obsidian/build_obsidian.py",
}

FOLLOW_UPS = {
    "import_paper":       ("update_paper_index", "documentation"),
    "update_paper_index": ("update_obsidian", "documentation"),
    "run_experiment":     ("update_dashboard", "dashboard"),
    "update_dashboard":   ("update_obsidian", "documentation"),
}

TIMEOUT = 300


def parse_action(task):
    """inputs: '<action>: <args>' -> (action, argv) or (None, None)."""
    raw = (task.inputs or "").strip()
    if not raw:
        return None, None
    head, _, rest = raw.partition(":")
    action = head.strip()
    if action not in ACTIONS:
        return None, None
    try:
        argv = shlex.split(rest.strip()) if rest.strip() else []
    except ValueError:
        argv = rest.strip().split()
    return action, argv


def _follow_up_exists(action):
    """Idempotency: an equivalent non-terminal task already in the queue?"""
    for _, t in q.load_all():
        a, _argv = parse_action(t)
        if a == action and t.status not in TERMINAL:
            return t.id
    return None


def queue_follow_up(action):
    nxt = FOLLOW_UPS.get(action)
    if not nxt:
        return None
    nxt_action, nxt_type = nxt
    dup = _follow_up_exists(nxt_action)
    if dup:
        return f"(follow-up {nxt_action} already queued as {dup})"
    path, t = q.create(f"Auto: {nxt_action.replace('_', ' ')}",
                       type_=nxt_type, priority="P2")
    # set the action on the new task
    t.inputs = f"{nxt_action}:"
    q.save(path, t)
    return f"queued follow-up {t.id} ({nxt_action})"


def execute(path, task):
    """Run the task's mapped script. Returns True if it executed (regardless of
    pass/fail); False if the task has no recognized action."""
    action, argv = parse_action(task)
    if action is None:
        return False
    script = os.path.join(REPO, ACTIONS[action])
    if not os.path.exists(script):
        rc, out, err, dur = 127, "", f"mapped script missing: {ACTIONS[action]}", 0.0
    else:
        t0 = time.time()
        try:
            r = subprocess.run([PY, script] + argv, cwd=REPO, capture_output=True,
                               text=True, timeout=TIMEOUT)
            rc, out, err = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            rc, out, err = 124, "", f"timeout after {TIMEOUT}s"
        dur = time.time() - t0

    ok = (rc == 0)
    task.status = "completed" if ok else "review"
    task.artifacts = (task.artifacts + "; " if task.artifacts else "") + \
        f"exec {datetime.now().strftime('%Y-%m-%d %H:%M')} rc={rc}"
    note = ""
    if ok:
        msg = queue_follow_up(action)
        if msg:
            note = f"\n- follow-up: {msg}"

    def clip(s, n=1500):
        s = (s or "").strip()
        return s if len(s) <= n else s[:n] + "\n... (clipped)"

    task.body += (
        f"\n## Execution log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- action: `{action}` -> `{ACTIONS[action]}`\n"
        f"- exit code: **{rc}** | duration: {dur:.2f}s | status -> **{task.status}**"
        f"{note}\n\n"
        f"### stdout\n```\n{clip(out)}\n```\n"
        f"### stderr\n```\n{clip(err) or '(empty)'}\n```\n")
    q.save(path, task)
    print(f"EXECUTED {task.id} [{action}] rc={rc} {dur:.2f}s -> {task.status}"
          + (f" | {note.strip()}" if note else ""))
    return True
