"""launcher_core.py -- Trading OS launcher engine (stdlib only, no GUI).

Presentation + launcher layer ONLY. Reuses existing scripts/artifacts; never
recomputes what command_center.py / status.py / evidence_report.py already do,
never writes to production/research/fills. The only writes are: launcher.log,
the session-restore file, and shelling EXISTING utilities on request.

Importable and testable without any GUI toolkit.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
import webbrowser
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SUPPORT = Path.home() / "Library" / "Application Support" / "TradingOS"
SETTINGS_FILE = HERE / "settings.json"
LOG = HERE / "launcher.log"
SESSION = SUPPORT / "session.json"

DEFAULTS = {
    "repo_path": str(REPO),
    "vault_path": str(REPO / "vault"),
    "dashboard_url": "http://localhost:8501",
    "dashboard_port": 8501,
    "auto_launch_dashboard": True,
    "auto_open_browser": True,
    "launch_vscode": True,
    "launch_obsidian": True,
    "launch_terminal": False,
    "auto_git_pull": False,
    "refresh_interval": 30,
    "vps_host": "188.190.4.122",
    "external": {
        "GitHub": "https://github.com/colindayer-boop/nas100-trader",
        "Claude": "https://claude.ai",
        "OpenClaw": "https://openclaw.ai",
        "OpenAI": "https://chat.openai.com",
        "Perplexity": "https://perplexity.ai",
    },
}


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass


def settings() -> dict:
    s = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            s.update(json.loads(SETTINGS_FILE.read_text()))
    except Exception as e:
        log(f"settings read failed, using defaults: {e}")
    # never trust a stale hardcoded repo path -- fall back to this file's repo
    if not Path(s["repo_path"]).exists():
        log(f"configured repo_path missing ({s['repo_path']}); using {REPO}")
        s["repo_path"] = str(REPO)
    return s


def repo() -> Path:
    return Path(settings()["repo_path"])


# ---------------------------------------------------------------- health --
def dashboard_health(url: str | None = None) -> str:
    """GREEN if the existing Streamlit server answers /_stcore/health, else RED."""
    url = url or settings()["dashboard_url"]
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/_stcore/health", timeout=2) as r:
            return "GREEN" if r.status == 200 and b"ok" in r.read().lower() else "YELLOW"
    except Exception:
        return "RED"


def dashboard_running() -> bool:
    return dashboard_health() == "GREEN"


def start_dashboard(wait_secs: int = 10) -> str:
    """Reuse a running dashboard; only launch if none is healthy. Never duplicates."""
    if dashboard_running():
        log("dashboard already running -- reusing")
        return "GREEN"
    s = settings()
    app = repo() / "dashboard" / "app.py"
    if not app.exists():
        log(f"dashboard app missing: {app}")
        return "MISSING"
    try:
        subprocess.Popen(
            ["python3", "-m", "streamlit", "run", str(app),
             "--server.headless", "true", "--server.port", str(s["dashboard_port"])],
            cwd=str(repo()), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        log("launched streamlit dashboard")
    except Exception as e:
        log(f"dashboard launch failed: {e}")
        return "RED"
    for _ in range(wait_secs * 2):
        if dashboard_running():
            return "GREEN"
        time.sleep(0.5)
    return "YELLOW"  # started but not healthy yet


def restart_dashboard() -> str:
    try:
        subprocess.run(["pkill", "-f", "streamlit run"], capture_output=True)
        log("killed existing streamlit")
        time.sleep(1)
    except Exception as e:
        log(f"restart kill failed: {e}")
    return start_dashboard()


# --------------------------------------------------------------- git ------
def git_info() -> dict:
    def g(*a):
        try:
            return subprocess.run(["git", *a], cwd=str(repo()), capture_output=True,
                                  text=True, timeout=8).stdout.strip()
        except Exception:
            return ""
    dirty = bool(g("status", "--porcelain"))
    ab = g("rev-list", "--left-right", "--count", "HEAD...@{u}") or "0\t0"
    ahead, behind = (ab.split("\t") + ["0", "0"])[:2]
    head_path = repo() / ".git" / "FETCH_HEAD"
    last_pull = (datetime.fromtimestamp(head_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                 if head_path.exists() else "unknown")
    return {"branch": g("branch", "--show-current") or "?",
            "commit": g("rev-parse", "--short", "HEAD") or "?",
            "state": "DIRTY" if dirty else "CLEAN",
            "ahead": ahead, "behind": behind, "last_pull": last_pull}


# --------------------------------------------------- status (reuse only) --
def _read(rel: str) -> str:
    p = repo() / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def status_cards() -> dict:
    """Green/Yellow/Red/Unknown per subsystem -- from EXISTING artifacts only.
    Regenerates COMMAND_CENTER via the existing script (no recomputation here)."""
    try:
        subprocess.run(["python3", "scripts/ops/command_center.py"], cwd=str(repo()),
                       capture_output=True, timeout=30)
    except Exception as e:
        log(f"command_center refresh failed: {e}")
    cc = _read("dashboard/COMMAND_CENTER.md")
    import re
    health = (re.search(r"SYSTEM HEALTH: \*\*(\w+)\*\*", cc) or [None, "UNKNOWN"])[1]
    ledger_today = f"| {date.today().isoformat()} |" in _read("docs/EVIDENCE_LEDGER.md")
    sh = _read("research/results/shadow_signals.csv")
    bl = re.search(r"SHADOW (\d+) \| WAITING (\d+)", _read("docs/RESEARCH_BACKLOG.md"))
    return {
        "Dashboard": dashboard_health(),
        "Git": "GREEN" if git_info()["state"] == "CLEAN" else "YELLOW",
        "Telegram": "UNKNOWN",   # requires config.ini / VPS -- never fake green
        "MT5": "UNKNOWN",        # Windows/VPS only
        "VPS": "UNKNOWN",        # not reachable from this host
        "Scheduler": "GREEN" if ledger_today else "YELLOW",
        "Research": "GREEN" if bl else "UNKNOWN",
        "Evidence": "GREEN" if health == "GREEN" else ("RED" if "ACTION" in health else "YELLOW"),
        "Shadow": "GREEN" if sh.strip() else "YELLOW",
        "Prop readiness": "YELLOW",  # DESIGN READY / EVIDENCE PENDING (per PROP_READINESS)
    }


def today_actions() -> list[str]:
    """<=3 rule-driven actions -- lifted verbatim from command_center's TODAY block."""
    import re
    cc = _read("dashboard/COMMAND_CENTER.md")
    m = re.search(r"## 6\. TODAY\n(.*?)(?=\n## )", cc, re.S)
    if not m:
        return ["Nothing required today."]
    items = [l.strip("- ").strip() for l in m.group(1).splitlines() if l.strip().startswith("-")]
    return items[:3] or ["Nothing required today."]


# --------------------------------------------------- launch primitives ----
def open_url(url: str) -> None:
    try:
        webbrowser.open(url)
        log(f"opened {url}")
    except Exception as e:
        log(f"open_url failed {url}: {e}")


def open_dashboard(path: str = "") -> None:
    start_dashboard()
    open_url(settings()["dashboard_url"].rstrip("/") + ("/" + path if path else ""))


def open_app(app_path: str, args: list[str] | None = None) -> bool:
    if not Path(app_path).exists():
        log(f"app not installed: {app_path}")
        return False
    try:
        subprocess.run(["open", "-a", app_path, *(args or [])], capture_output=True)
        log(f"launched {app_path}")
        return True
    except Exception as e:
        log(f"open_app failed {app_path}: {e}")
        return False


def launch_obsidian() -> bool:
    return open_app("/Applications/Obsidian.app", [settings()["vault_path"]])


def launch_vscode() -> bool:
    return open_app("/Applications/Visual Studio Code.app", [settings()["repo_path"]])


def launch_terminal() -> bool:
    try:
        subprocess.run(["open", "-a", "Terminal", settings()["repo_path"]], capture_output=True)
        log("launched Terminal at repo")
        return True
    except Exception as e:
        log(f"terminal launch failed: {e}")
        return False


def open_file(rel: str) -> None:
    p = repo() / rel
    if p.exists():
        subprocess.run(["open", str(p)], capture_output=True)
        log(f"opened file {rel}")
    else:
        log(f"open_file missing: {rel}")


def open_vps_rdp() -> None:
    open_url(f"rdp://{settings()['vps_host']}")


# --------------------------------------------------- quick actions --------
QUICK = {  # label -> (existing script/command, args). REUSE, never reimplement.
    "Git Pull":                (["git", "pull", "--ff-only"], True),
    "Git Status":              (["git", "status"], True),
    "Generate Command Center": (["python3", "scripts/ops/command_center.py"], True),
    "Generate Evidence Report":(["python3", "scripts/ops/evidence_report.py", "--daily"], True),
    "Run Status Check":        (["python3", "status.py"], True),
    "Run Parity Audit":        (["python3", "tools/audit_signal_parity.py"], True),
}


def run_quick(label: str) -> str:
    cmd, _ = QUICK.get(label, (None, None))
    if not cmd:
        return f"unknown action: {label}"
    try:
        r = subprocess.run(cmd, cwd=str(repo()), capture_output=True, text=True, timeout=120)
        log(f"quick action '{label}' rc={r.returncode}")
        return (r.stdout or r.stderr or "(no output)")[-4000:]
    except Exception as e:
        log(f"quick action '{label}' failed: {e}")
        return str(e)


# --------------------------------------------------- live status feed -----
def live_status() -> dict:
    import csv
    import re

    def last_csv(rel, ts="timestamp_utc"):
        p = repo() / rel
        if not p.exists() or p.stat().st_size == 0:
            return "none"
        rows = list(csv.DictReader(open(p, encoding="utf-8", errors="replace")))
        return rows[-1].get(ts, "?") if rows else "none"

    inc = repo() / "vault" / "08-Incidents-and-Postmortems"
    incidents = sorted((f.stem for f in inc.glob("*.md") if f.stem[0].isdigit()), reverse=True) if inc.is_dir() else []
    ledger = [l for l in _read("docs/EVIDENCE_LEDGER.md").splitlines() if l.startswith("| 20")]
    return {
        "latest_fill": last_csv("logs/fills.csv"),
        "latest_shadow": last_csv("research/results/shadow_signals.csv", "date"),
        "latest_evidence": (ledger[-1][:40] if ledger else "none"),
        "latest_commit": git_info()["commit"],
        "latest_incident": (incidents[0] if incidents else "none"),
    }


# --------------------------------------------------- session restore ------
def save_session(state: dict) -> None:
    try:
        SUPPORT.mkdir(parents=True, exist_ok=True)
        SESSION.write_text(json.dumps({**state, "saved": datetime.now().isoformat()}))
    except Exception as e:
        log(f"save_session failed: {e}")


def load_session() -> dict:
    try:
        return json.loads(SESSION.read_text()) if SESSION.exists() else {}
    except Exception:
        return {}


# --------------------------------------------------- startup orchestration -
def startup() -> dict:
    """The 6 startup steps. Idempotent, never blocks the UI, honest about failures."""
    s = settings()
    result = {"dashboard": "skipped", "git": {}, "obsidian": False, "vscode": False,
              "terminal": False, "restored": False}
    log("=== Trading OS startup ===")
    if s["auto_git_pull"]:
        run_quick("Git Pull")
    if s["auto_launch_dashboard"]:
        result["dashboard"] = start_dashboard()
        if s["auto_open_browser"] and result["dashboard"] in ("GREEN", "YELLOW"):
            open_url(s["dashboard_url"])
    result["git"] = git_info()
    if s["launch_obsidian"]:
        result["obsidian"] = launch_obsidian()
    if s["launch_vscode"]:
        result["vscode"] = launch_vscode()
    if s["launch_terminal"]:
        result["terminal"] = launch_terminal()
    prev = load_session()
    result["restored"] = bool(prev)
    save_session({"last_startup": datetime.now().isoformat(), "opened": ["dashboard"]})
    log(f"startup complete: {result['dashboard']}")
    return result


if __name__ == "__main__":
    import pprint
    pprint.pprint(startup())
