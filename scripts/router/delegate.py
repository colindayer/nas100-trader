"""delegate.py -- one-command multi-model delegation (execution layer of the
existing bridge). Reuses llm_bridge (brief/handoff), queue (tasks), state (router
state). NOT a second framework: it wires the DISCOVERED backend commands to the
existing task pipeline.

Usage (via task_router.py):
    delegate TASK-ID [--backend qwen|qwen-deep|glm|auto] [--force]
    bridge-status

Safety: backends run as fixed argv lists (never shell=True, never model-controlled
commands). Model output is untrusted text -- only written to a reply file and
validated against the response contract; it can never edit production or run shell.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import queue as q            # noqa: E402
import state as st_mod       # noqa: E402
from models import parse     # noqa: E402

REPO = q.REPO
HANDOFF = os.path.join(REPO, "research", "handoffs")
UID = os.getuid()
OLLAMA = "/opt/homebrew/bin/ollama" if os.path.exists("/opt/homebrew/bin/ollama") else (shutil.which("ollama") or "ollama")
OPENCLAW = shutil.which("openclaw") or os.path.expanduser("~/.nvm/versions/node/v24.18.0/bin/openclaw")
OLLAMA_API = "http://127.0.0.1:11434/api/tags"
TIMEOUTS = {"qwen": 180, "qwen-deep": 420, "glm": 600}

# DISCOVERED backend commands only. {brief} is substituted with the brief PATH for
# file-input backends; stdin backends receive the brief text on stdin.
BACKENDS = {
    "qwen":      {"model": "qwen2.5-coder:7b",  "argv": [OLLAMA, "run", "qwen2.5-coder:7b"],  "input": "stdin", "ollama": True},
    "qwen-deep": {"model": "qwen2.5-coder:14b", "argv": [OLLAMA, "run", "qwen2.5-coder:14b"], "input": "stdin", "ollama": True},
    # --session-key required (gateway rejects without a target session); pinned live 2026-07-14
    "glm":       {"model": "glm-5.2", "argv": [OPENCLAW, "agent", "--model", "glm-5.2", "--message-file", "{brief}", "--json", "--session-key", "delegate-{task}"], "input": "file", "ollama": False},
}

CONTRACT = """
## RESPONSE CONTRACT — reply with EXACTLY these four sections, in this order:
# Findings
# Evidence
# Risks
# Recommendation

The Recommendation section must contain exactly ONE of these tokens on its own line:
NO_ACTION | INVESTIGATE | CREATE_EXPERIMENT | REVIEW_REQUIRED | REJECT

You are a READ-ONLY analyst. Do not propose code edits, shell commands, commits, or
trades. Do not invent data. If context is insufficient, say exactly what you need.
"""
VALID_RECS = {"NO_ACTION", "INVESTIGATE", "CREATE_EXPERIMENT", "REVIEW_REQUIRED", "REJECT"}
_SECRET = re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?token)\s*[:=]")


# ---------------------------------------------------------------- routing --
def auto_route(task) -> tuple[str, str]:
    """Deterministic: one task -> one primary backend. Documented keyword rules."""
    text = f"{task.title} {task.inputs} {task.body}".lower()
    glm_kw = ("paper", "literature", "macro", "research review", "synthesis",
              "independent", "long-context", "critique", "experiment critique")
    deep_kw = ("adversarial", "multi-file", "implementation review", "compare",
               "repository-wide", "forensic", "code review", "reasoning")
    light_kw = ("log", "index", "extract", "summar", "classif", "search",
                "links", "documentation", "structured facts")
    if any(k in text for k in glm_kw):
        return "glm", "auto: papers/literature/macro/independent-research keyword"
    if any(k in text for k in deep_kw):
        return "qwen-deep", "auto: multi-path/adversarial/repo-wide reasoning keyword"
    if any(k in text for k in light_kw):
        return "qwen", "auto: logs/extraction/summary/search keyword"
    return "qwen", "auto: default local worker (no research/deep signal)"


# ---------------------------------------------------------------- ollama ---
def ollama_up() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_API, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_ollama(wait: int = 30) -> tuple[bool, str]:
    """Reuse the existing LaunchAgent; never spawn a second server; bounded wait."""
    if ollama_up():
        return True, "already up"
    try:
        subprocess.run(["launchctl", "kickstart", "-k", f"gui/{UID}/com.colindayer.ollama"],
                       capture_output=True, timeout=10)
    except Exception as e:
        return False, f"launchctl kickstart failed: {e}"
    deadline = time.time() + wait
    while time.time() < deadline:
        if ollama_up():
            return True, "kickstarted"
        time.sleep(1)
    return False, f"ollama still unavailable after {wait}s (check LaunchAgent com.colindayer.ollama)"


# ---------------------------------------------------------------- brief ----
def _safe_ctx() -> str:
    """Small context, secrets stripped. NEVER reads config.ini."""
    p = os.path.join(REPO, "docs", "CURRENT_PROJECT_STATE.md")
    if not os.path.exists(p):
        return ""
    lines = [l for l in open(p, encoding="utf-8", errors="replace").read()[:5000].splitlines()
             if not _SECRET.search(l)]
    return "\n".join(lines)


def build_brief(task, backend: str, correction: str = "") -> tuple[str, str]:
    owner = {"qwen": "Qwen", "qwen-deep": "Qwen", "glm": "GLM"}[backend]
    outdir = os.path.join(HANDOFF, owner)
    os.makedirs(outdir, exist_ok=True)
    text = (f"# TASK BRIEF for {owner} ({BACKENDS[backend]['model']}) -- {task.id}\n\n"
            f"You are a read-only analyst in a trading-research system. Claude is the "
            f"final reviewer; your reply is ingested for a human to read.\n\n"
            f"## Task\n**{task.title}**\n\n{task.body.strip()[:3000]}\n\n"
            f"## Inputs\n`{task.inputs}`\n\n"
            f"---- CONTEXT: docs/CURRENT_PROJECT_STATE.md (truncated, secrets stripped) ----\n"
            f"{_safe_ctx()}\n"
            + (f"\n## CORRECTION\n{correction}\n" if correction else "")
            + CONTRACT)
    assert not _SECRET.search(text), "refusing to write a brief containing a secret marker"
    path = os.path.join(outdir, f"{task.id}-BRIEF.md")
    open(path, "w", encoding="utf-8").write(text)
    return path, text


# ---------------------------------------------------------------- contract -
def validate(text: str) -> tuple[bool, str, str]:
    for h in ("# Findings", "# Evidence", "# Risks", "# Recommendation"):
        if h not in text:
            return False, "", f"missing section '{h}'"
    tail = text.split("# Recommendation", 1)[1]
    recs = [r for r in VALID_RECS if re.search(rf"(^|\W){re.escape(r)}(\W|$)", tail)]
    if len(recs) != 1:
        return False, "", f"recommendation must be exactly one of {sorted(VALID_RECS)} (found {recs})"
    return True, recs[0], "ok"


# ---------------------------------------------------------------- execute --
def run_backend(backend: str, brief_path: str, brief_text: str, task_id: str = "task") -> dict:
    b = BACKENDS[backend]
    argv = [a.replace("{brief}", brief_path).replace("{task}", task_id) for a in b["argv"]]
    stdin = brief_text if b["input"] == "stdin" else None
    t0 = time.time()
    try:
        r = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                           timeout=TIMEOUTS[backend])  # shell=False; model text never in argv
        rc, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = 124, "", f"timeout after {TIMEOUTS[backend]}s"
    except FileNotFoundError as e:
        rc, out, err = 127, "", f"backend executable missing: {e}"
    return {"rc": rc, "stdout": out, "stderr": err, "dur": round(time.time() - t0, 1),
            "model": b["model"], "cmd": " ".join(argv)}


def _reply_text(backend: str, res: dict) -> str:
    """GLM returns JSON; extract the text. Qwen returns raw text."""
    if backend == "glm" and res["stdout"].strip().startswith("{"):
        try:
            j = json.loads(res["stdout"])
            # openclaw shape: result.payloads[*].text (pinned live 2026-07-14)
            pls = j.get("result", {}).get("payloads", [])
            texts = [p["text"] for p in pls if isinstance(p, dict) and isinstance(p.get("text"), str)]
            if texts:
                return "\n".join(texts)
            for k in ("text", "message", "reply", "content", "output"):
                if isinstance(j.get(k), str):
                    return j[k]
            return json.dumps(j)
        except Exception:
            return res["stdout"]
    return res["stdout"]


# ---------------------------------------------------------------- delegate -
def delegate(task_id: str, backend: str = "auto", force: bool = False):
    path = q.task_path(task_id)
    if not path:
        raise SystemExit(f"task not found: {task_id}")
    task = parse(open(path, encoding="utf-8").read())
    if task.status in ("completed", "approved", "rejected") and not force:
        print(f"{task_id} is {task.status} -- not re-running without --force")
        return
    if backend == "auto":
        backend, reason = auto_route(task)
    else:
        reason = "explicit --backend"
    if backend not in BACKENDS:
        raise SystemExit(f"unknown backend '{backend}' (choose {list(BACKENDS)} or auto)")

    owner = {"qwen": "Qwen", "qwen-deep": "Qwen", "glm": "GLM"}[backend]
    meta = {"task": task_id, "backend": backend, "model": BACKENDS[backend]["model"],
            "start": datetime.now().isoformat(timespec="seconds"), "routing_reason": reason,
            "retry_count": 0}
    print(f"delegate {task_id} -> {backend} ({BACKENDS[backend]['model']}) | {reason}")

    if BACKENDS[backend]["ollama"]:
        ok, why = ensure_ollama()
        if not ok:
            return _finish(path, task, meta, "blocked", f"ollama unavailable: {why}", None, None)

    def attempt(bk, correction=""):
        bp, bt = build_brief(task, bk, correction)
        res = run_backend(bk, bp, bt, task_id)
        reply = _reply_text(bk, res)
        rp = os.path.join(HANDOFF, owner, f"{task_id}-REPLY.md")
        open(rp, "w", encoding="utf-8").write(reply)
        so = os.path.join(HANDOFF, owner, f"{task_id}-STDERR.log")
        open(so, "w", encoding="utf-8").write(res["stderr"] or "")
        return res, reply, bp, rp, so

    res, reply, bp, rp, so = attempt(backend)
    meta.update(brief=os.path.relpath(bp, REPO), reply=os.path.relpath(rp, REPO),
                stderr=os.path.relpath(so, REPO), duration=res["dur"],
                exit_code=res["rc"], cmd=res["cmd"])

    if res["rc"] != 0:
        return _finish(path, task, meta, "blocked",
                       f"backend exit {res['rc']}: {res['stderr'][:200]}", None, reply)

    ok, rec, why = validate(reply)
    # retry once (same backend) on contract failure
    if not ok:
        meta["retry_count"] = 1
        res, reply, bp, rp, so = attempt(backend,
            "Your previous reply did not satisfy the contract: " + why)
        meta.update(duration=res["dur"], exit_code=res["rc"])
        ok, rec, why = validate(reply)
    # contract-fail fallback 7b -> 14b (only permitted escalation)
    if not ok and backend == "qwen":
        meta["retry_count"] = 2
        meta["routing_reason"] += " | escalated qwen->qwen-deep (contract fail)"
        backend = "qwen-deep"; owner = "Qwen"
        res, reply, bp, rp, so = attempt(backend)
        meta.update(backend=backend, model=BACKENDS[backend]["model"],
                    duration=res["dur"], exit_code=res["rc"], cmd=res["cmd"])
        ok, rec, why = validate(reply)

    if not ok:
        return _finish(path, task, meta, "review",
                       f"INVALID response contract: {why} (reply kept for debugging)", None, reply)
    meta["recommendation"] = rec
    return _finish(path, task, meta, "review", "ok", rec, reply)


def _finish(path, task, meta, status, note, rec, reply):
    meta["validation"] = note
    task.status = status
    if reply is not None and status == "review" and note == "ok":
        task.body += (f"\n## Delegated reply -- {meta['backend']} ({meta['model']}) "
                      f"{meta['start']} -- rec: {rec}\n\n{reply[:8000]}\n")
    task.body += ("\n## Delegation log\n```json\n" + json.dumps(meta, indent=1) + "\n```\n")
    task.artifacts = (task.artifacts + "; " if task.artifacts else "") + \
        f"delegate {meta['backend']} rc={meta.get('exit_code')} -> {status}"
    q.save(path, task)
    # observability into router state (no second database)
    stt = st_mod.load()
    key = "last_success" if note == "ok" else "last_failure"
    stt.setdefault("delegations", {})[key] = meta
    st_mod.save(stt)
    print(f"{task.id}: {meta['backend']} rc={meta.get('exit_code')} "
          f"{meta.get('duration')}s -> {status} ({note})")
    return meta


# ---------------------------------------------------------------- status ---
def bridge_status():
    up = ollama_up()
    tags = []
    if up:
        try:
            with urllib.request.urlopen(OLLAMA_API, timeout=2) as r:
                tags = [m["name"] for m in json.load(r).get("models", [])]
        except Exception:
            pass
    have = lambda t: any(x.startswith(t) for x in tags)
    ocfg = os.path.expanduser("~/.openclaw/openclaw.json")
    zai = glm = False
    if os.path.exists(ocfg):
        try:
            d = json.load(open(ocfg))
            zai = any(p.get("provider") == "zai" for p in d.get("auth", {}).get("profiles", {}).values())
            glm = any(m.get("id") == "glm-5.2" for pv in d.get("models", {}).get("providers", {}).values()
                      for m in pv.get("models", []))
        except Exception:
            pass
    stt = st_mod.load().get("delegations", {})
    S = lambda b: ("UP" if b else "DOWN")
    lines = [
        "=== BRIDGE STATUS ===",
        f"Claude (lead/rev)  : {S(bool(shutil.which('claude')))} (never auto-delegated)",
        f"Ollama daemon      : {S(up)} ({OLLAMA_API})",
        f"Qwen 7B available  : {S(have('qwen2.5-coder:7b') or (up and 'qwen2.5-coder' in ' '.join(tags)))}",
        f"Qwen 14B available : {S(have('qwen2.5-coder:14b'))}" + ("" if up else " (daemon down -- from disk on start)"),
        f"OpenClaw available : {S(bool(shutil.which('openclaw') or os.path.exists(OPENCLAW)))}",
        f"Z.ai provider      : {S(zai)} (configured in openclaw.json)",
        f"GLM model (glm-5.2): {S(glm)}",
        f"last success       : {stt.get('last_success', {}).get('task', 'none')} "
        f"({stt.get('last_success', {}).get('backend','-')})",
        f"last failure       : {stt.get('last_failure', {}).get('task', 'none')} "
        f"({stt.get('last_failure', {}).get('validation','-')})",
    ]
    print("\n".join(lines))
    return {"ollama": up, "tags": tags, "zai": zai, "glm": glm}
