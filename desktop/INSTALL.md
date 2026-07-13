# Trading OS — the desktop launcher

**One icon. Click it. Your whole trading workspace is ready.** No terminal, no
`streamlit run`, no `cd`, no remembering the dashboard URL.

Trading OS is a thin native macOS **launcher shell** over the system that already
exists — it launches/reuses the Streamlit dashboard, opens Obsidian/VSCode, runs the
existing utilities, and shows health in the menu bar. It never re-implements or
duplicates any trading, research, evidence, or dashboard logic.

## What it does on launch (< 10s target)
1. **Dashboard** — if one is already running on :8501 it *reuses* it (never a
   duplicate); otherwise launches `streamlit run dashboard/app.py`, waits until
   healthy, opens the browser.
2. **Git** — shows branch / commit / clean-dirty / ahead-behind / last pull.
3. **Obsidian** — opens the Trading Vault (if installed; warns if not).
4. **VSCode** — opens the repo (if installed).
5. **Terminal** — opens at the repo (off by default; toggle in settings).
6. **Session restore** — remembers what was open.

## Install
```bash
# one time, from the repo root:
./desktop/build_app.sh --install
```
This builds `Trading OS.app` and copies it to `/Applications`. It stamps the current
repo path into `desktop/settings.json` (no hardcoded paths). After that you never
touch the terminal — just open **Trading OS** from Applications / Spotlight.

Build without installing (bundle lands in `desktop/dist/`):
```bash
./desktop/build_app.sh
```

## Dependencies
- **Required:** macOS 12+, `python3`, and the environment where `streamlit` is
  installed (the same one you already use for the dashboard).
- **Menu-bar icon (recommended):** `pip3 install rumps`
  Without rumps the app still works — it runs the one-click startup (dashboard +
  tools) and exits; you just don't get the persistent menu-bar icon.
- **Auto-detected, optional:** Obsidian, VSCode. Missing apps are handled gracefully
  (a log line, never a crash).

## Menu-bar icon (with rumps)
- 🟢 dashboard healthy · 🟡 starting/degraded · 🔴 stopped · ⚪️ unknown
- **Click** → menu: Open Dashboard, Trade Explorer, Knowledge Graph, Restart, Launch
  (Obsidian/VSCode/Terminal/VPS/GitHub/Claude/OpenClaw/OpenAI/Perplexity), Quick
  Actions (git pull/status, generate command center/evidence report, status check,
  parity audit), Report Center (all the docs), Today, Quit.

## Update
The app runs the *live* repo copy — so `git pull` (or the app's Quick Action → Git
Pull) updates everything, no rebuild needed. Rebuild the bundle only if you move the
repo: re-run `./desktop/build_app.sh --install`.

## Settings — `desktop/settings.json`
`repo_path`, `vault_path`, `dashboard_url`/`dashboard_port`, and toggles for
auto-launch dashboard / auto-open browser / launch VSCode / launch Obsidian / launch
Terminal / auto git pull / refresh interval / vps_host. Edit and relaunch.

## Recovery
- Streamlit crashed → menu **Restart Dashboard**.
- Browser closed → **Open Dashboard** reopens it.
- Dashboard unavailable → the icon goes 🔴 and the reason is in `desktop/launcher.log`.
- VPS is not reachable from the Mac → shown **UNKNOWN** (never fake-green).

## Logs
`desktop/launcher.log` — startup, launches, failures, restarts. No production
logging is changed.

## What it never does
No production/strategy/research/evidence code is modified. The app is read-only
except for: `launcher.log`, the session-restore file (in `~/Library/Application
Support/TradingOS/`), and shelling the **existing** utilities you'd otherwise run by
hand. It duplicates none of `command_center.py`, `evidence_report.py`, `status.py`,
or any dashboard calculation — it calls them and reads their artifacts.
