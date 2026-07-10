"""
task_router.py -- the AI Task Router (orchestration layer ABOVE production).

Dispatches queued tasks to the right AI system. It NEVER performs work and NEVER
touches production code -- it reads/writes ONLY research/queue/TASK-*.md files
and state/router_state.json.

Usage:
    python scripts/router/task_router.py run                 # scan, sort, assign
    python scripts/router/task_router.py run --dry-run       # show what would happen
    python scripts/router/task_router.py new "Title" --type paper --priority P1
    python scripts/router/task_router.py list                # queue overview
    python scripts/router/task_router.py set TASK-... --status review|approved|...

Routing (dispatch.py): implementation->Claude, research->GLM, paper->Qwen,
review->Fable, ops/monitoring->OpenClaw, dashboard->GLM, documentation->Claude.

Idempotency: only status=queued tasks are dispatched; assignment flips them to
running with an owner. Re-running assigns nothing new, duplicates nothing, and
appends a run record to state. Task BODIES are passed through verbatim
(human notes below the frontmatter are never overwritten).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Task, STATUSES, TYPES, PRIORITIES, TERMINAL   # noqa: E402
import queue as q                                                 # noqa: E402
import dispatch                                                   # noqa: E402
import state as st_mod                                            # noqa: E402
import executor                                                   # noqa: E402


def cmd_run(args):
    tasks = q.load_all()
    st = st_mod.load()
    queued = [(p, t) for p, t in tasks if t.status == "queued"]
    skipped = [t.id for _, t in tasks if t.status != "queued"]
    # deterministic order: priority (P0 first), then id (oldest first)
    queued.sort(key=lambda pt: (PRIORITIES.index(pt[1].priority)
                                if pt[1].priority in PRIORITIES else 99, pt[1].id))
    assigned = []
    for path, t in queued:
        # dependency gate: don't dispatch if a named dependency is not terminal
        deps = [d.strip() for d in t.dependencies.split(",") if d.strip()]
        unmet = []
        for d in deps:
            dep = next((x for _, x in tasks if x.id == d), None)
            if dep is None or dep.status not in TERMINAL:
                unmet.append(d)
        if unmet:
            print(f"HOLD  {t.id} [{t.priority}/{t.type}] waiting on: {', '.join(unmet)}")
            skipped.append(t.id)
            continue
        owner = dispatch.choose(t)
        if args.dry_run:
            print(f"WOULD ASSIGN {t.id} [{t.priority}/{t.type}] -> {owner}")
            continue
        t.owner = owner
        t.status = "running"
        q.save(path, t)
        assigned.append(t)
        print(f"ASSIGNED {t.id} [{t.priority}/{t.type}] -> {owner}")
        # automatic execution: if the task's `inputs` names a known action,
        # run the mapped existing script now (capture rc/stdout/stderr/time,
        # auto-update status, queue follow-ups). Tasks without a recognized
        # action stay `running` for their assigned AI to pick up manually.
        if not args.assign_only:
            executor.execute(path, t)
    if not args.dry_run:
        # follow-up tasks created during execution are dispatched on the NEXT
        # run (keeps each run bounded and auditable). Run twice to drain a chain.
        st_mod.save(st_mod.record_run(st, assigned, skipped))
    print(f"run complete: {len(assigned)} assigned, "
          f"{len(skipped)} skipped (non-queued/held)")


def cmd_new(args):
    path, t = q.create(args.title, type_=args.type, priority=args.priority,
                       inputs=args.inputs, outputs=args.outputs,
                       dependencies=args.dependencies, reviewer=args.reviewer)
    print(f"created {os.path.relpath(path, q.REPO)}  (id={t.id}, status=queued)")


def cmd_list(_args):
    tasks = q.load_all()
    if not tasks:
        print("(queue empty)")
        return
    for _, t in sorted(tasks, key=lambda pt: pt[1].id):
        print(f"{t.id}  {t.status:9} {t.priority} {t.type:14} "
              f"owner={t.owner or '-':9} {t.title[:50]}")


def cmd_set(args):
    path = q.task_path(args.task_id)
    if not path:
        print(f"NOT FOUND: {args.task_id}")
        sys.exit(1)
    t = q.load_all()
    t = next((x for p, x in t if p == path), None)
    if args.status not in STATUSES:
        print(f"bad status (choose from {STATUSES})")
        sys.exit(1)
    t.status = args.status
    if args.owner:
        t.owner = args.owner
    q.save(path, t)
    print(f"{t.id} -> status={t.status}" + (f", owner={t.owner}" if args.owner else ""))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--assign-only", action="store_true",
                   help="dispatch owners but skip automatic execution")
    r.set_defaults(fn=cmd_run)

    n = sub.add_parser("new")
    n.add_argument("title")
    n.add_argument("--type", default="research", choices=TYPES)
    n.add_argument("--priority", default="P2", choices=PRIORITIES)
    n.add_argument("--inputs", default="")
    n.add_argument("--outputs", default="")
    n.add_argument("--dependencies", default="", help="comma-separated TASK ids")
    n.add_argument("--reviewer", default="")
    n.set_defaults(fn=cmd_new)

    l = sub.add_parser("list")
    l.set_defaults(fn=cmd_list)

    s = sub.add_parser("set")
    s.add_argument("task_id")
    s.add_argument("--status", required=True)
    s.add_argument("--owner", default="")
    s.set_defaults(fn=cmd_set)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
