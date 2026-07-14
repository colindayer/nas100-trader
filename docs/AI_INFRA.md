# LOCAL AI INFRASTRUCTURE — architecture

_Infrastructure only. No trading/strategy/risk/execution logic. How every model is
used, when each is selected, and how to add another backend later._

## The pipeline (every task)
```
brief → route → execute → capture → validate → collect → review
```
One command runs it all: `python scripts/router/task_router.py delegate TASK-ID`.
Implemented in `scripts/router/delegate.py` (execution layer) on top of the existing
`llm_bridge` / `queue` / `state` / `research/handoffs/` — not a second framework.

## The models and when each is selected (deterministic auto-route)
| model | backend id | selected for | command (discovered + verified) |
|---|---|---|---|
| **Qwen 2.5-coder 7B** (local, free) | `qwen` | repo search, grep, docs, log parsing, small code reading, extraction, summaries | `cat {brief} \| ollama run qwen2.5-coder:7b` |
| **Qwen 2.5-coder 14B** (local, free) | `qwen-deep` | multi-file code reasoning, implementation comparison, architecture/adversarial review; contract-failure escalation from 7B | `... ollama run qwen2.5-coder:14b` |
| **GLM-5.2** (z.ai via OpenClaw) | `glm` | papers, macro, literature, long-context synthesis, independent reviewer | `openclaw agent --model glm-5.2 --message-file {brief} --json --session-key delegate-{task}` |
| **Claude** (lead engineer) | — | production code, architecture, commits, final review | **never auto-delegated** |

Routing keywords are in `delegate.auto_route()`. **One task → one primary backend.** A
second backend runs only on contract failure (7B→14B) — the reason is recorded.

## Response contract (enforced, not advisory)
Every reply must contain `# Findings`, `# Evidence`, `# Risks`, `# Recommendation`
with exactly one of `NO_ACTION | INVESTIGATE | CREATE_EXPERIMENT | REVIEW_REQUIRED |
REJECT`. Invalid replies are kept for debugging, retried once, then left at `review`
— never collected as valid, never allowed to touch production.

## Safety
Backends run as fixed argv lists (`shell=False`); model text never enters a command.
Model output is untrusted — only written to a reply file and validated. Briefs strip
secret markers and never read `config.ini`. Bounded timeouts (180/420/600s) and
bounded retries. No silent fallback to Claude.

## Ollama lifecycle
The bridge checks `http://127.0.0.1:11434/api/tags`; if down it `launchctl kickstart`s
the existing LaunchAgent `com.colindayer.ollama` (bounded 30s wait) — never spawns a
second server.

## Dashboard startup (why it used to refuse :8501)
`streamlit` lives in conda (`/opt/anaconda3/bin/streamlit`), not on the default
`python3`. The launcher now resolves a **streamlit executable that actually imports**
(`launcher_core.resolve_streamlit()`), pins it in `desktop/settings.json`
(`streamlit_bin`), and launches it directly — deterministic regardless of shell env.
Opening Trading OS → dashboard up → browser → HTTP 200, no troubleshooting.

## Observability
Per task: `## Delegation log` (backend, model, timings, exit, paths, recommendation,
retry count, routing reason). Global: `state/router_state.json` last success/failure.
`bridge-status` shows Claude / Ollama / Qwen 7B / Qwen 14B / OpenClaw / z.ai / GLM.

## Adding another backend later
1. Add an entry to `delegate.BACKENDS`: `{"model": ..., "argv": [EXE, ...,
   "{brief}"], "input": "stdin"|"file", "ollama": bool}` — use `{brief}` (path) and
   optional `{task}` placeholders; argv only, never a shell string.
2. Add its keywords to `delegate.auto_route()` (or leave it explicit-only).
3. Map its owner folder in `build_brief`/`delegate` (Qwen/GLM/…).
4. Add a `TIMEOUTS` entry and, if JSON, a parse branch in `_reply_text`.
5. Add a `bridge_status` line. Run `test_bridge.py` (mock) + one real smoke test.
No other file changes; the pipeline is backend-agnostic.

## Trading OS launcher
Menu → **Bridge**: Status · Restart Ollama · Test Qwen · Test GLM · Open Dashboard.
Reuses `launcher_core`; opens the existing Streamlit dashboard (no duplicate UI).
