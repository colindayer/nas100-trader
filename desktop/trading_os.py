"""trading_os.py -- Trading OS menu-bar application (macOS).

Thin native shell over the EXISTING system: launches/reuses the Streamlit
dashboard, opens tools, runs existing utilities. All logic lives in
launcher_core (reused, testable). The rich HOME / strategy panel / pipeline /
trade explorer / knowledge graph / report center already live IN the dashboard;
this app OPENS them, never re-implements them.

With `rumps` installed -> a real menu-bar app (green/yellow/red icon, dropdown
menu, quick actions). Without it -> runs the one-click startup and exits, the
dashboard stays up. Either way: click once, workspace ready.
"""
from __future__ import annotations

import sys
import threading

import launcher_core as core

MENU_URL = {  # label -> dashboard path (reuse existing pages, never rebuild)
    "Dashboard": "", "Trade Explorer": "", "Knowledge Graph": "",
}
DOC = {  # report-center one-click opens (existing docs)
    "Current Project State": "docs/CURRENT_PROJECT_STATE.md",
    "Project Constitution": "docs/PROJECT_CONSTITUTION.md",
    "Monthly Committee": "docs/MONTHLY_EVIDENCE_COMMITTEE.md",
    "Evidence Ledger": "docs/EVIDENCE_LEDGER.md",
    "Research Backlog": "docs/RESEARCH_BACKLOG.md",
    "Graveyard": "docs/RESEARCH_GRAVEYARD_AUDIT.md",
    "Validation Audit": "docs/STRATEGY_VALIDATION_AUDIT.md",
    "Data Lineage": "docs/DATA_LINEAGE.md",
    "Clock Reset Log": "docs/CLOCK_RESETS.md",
    "Prop Readiness": "docs/PROP_READINESS.md",
    "Repository Cleanup": "docs/REPO_CLEANUP.md",
    "Knowledge Graph (md)": "docs/KNOWLEDGE_GRAPH.md",
}
FILE = {  # quick file opens
    "Open Logs": "logs/trader.log", "Open fills.csv": "logs/fills.csv",
    "Open shadow log": "research/results/shadow_signals.csv",
}

ICON = {"GREEN": "🟢 Trading OS", "YELLOW": "🟡 Trading OS",
        "RED": "🔴 Trading OS", "UNKNOWN": "⚪️ Trading OS"}


def _run_bg(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


def build_menu_app():
    import rumps

    class TradingOS(rumps.App):
        def __init__(self):
            super().__init__("🟡 Trading OS", quit_button=None)
            s = core.settings()
            g = core.git_info()
            self.menu = [
                rumps.MenuItem(f"branch {g['branch']} @ {g['commit']} ({g['state']})"),
                None,
                rumps.MenuItem("Open Dashboard", callback=lambda _: _run_bg(core.open_dashboard)),
                rumps.MenuItem("Trade Explorer", callback=lambda _: _run_bg(core.open_dashboard)),
                rumps.MenuItem("Knowledge Graph", callback=lambda _: core.open_file("docs/KNOWLEDGE_GRAPH.md")),
                rumps.MenuItem("Restart Dashboard", callback=lambda _: _run_bg(core.restart_dashboard)),
                None,
                ("Launch", [rumps.MenuItem("Obsidian", callback=lambda _: core.launch_obsidian()),
                            rumps.MenuItem("VSCode", callback=lambda _: core.launch_vscode()),
                            rumps.MenuItem("Terminal", callback=lambda _: core.launch_terminal()),
                            rumps.MenuItem("VPS Remote Desktop", callback=lambda _: core.open_vps_rdp()),
                            rumps.MenuItem("GitHub", callback=lambda _: core.open_url(s["external"]["GitHub"])),
                            rumps.MenuItem("Claude", callback=lambda _: core.open_url(s["external"]["Claude"])),
                            rumps.MenuItem("OpenClaw", callback=lambda _: core.open_url(s["external"]["OpenClaw"])),
                            rumps.MenuItem("OpenAI", callback=lambda _: core.open_url(s["external"]["OpenAI"])),
                            rumps.MenuItem("Perplexity", callback=lambda _: core.open_url(s["external"]["Perplexity"]))]),
                ("Bridge", [rumps.MenuItem("Status", callback=self._bridge_status),
                            rumps.MenuItem("Restart Ollama", callback=lambda _: rumps.notification("Trading OS", "Bridge", core.restart_ollama())),
                            rumps.MenuItem("Test Qwen", callback=lambda _: _run_bg(lambda: rumps.notification("Trading OS", "Qwen", core.test_qwen()))),
                            rumps.MenuItem("Test GLM", callback=lambda _: _run_bg(lambda: rumps.notification("Trading OS", "GLM", core.test_glm())))]),
                ("Quick Actions", [rumps.MenuItem(k, callback=self._quick) for k in core.QUICK]),
                ("Evidence", [rumps.MenuItem("Evidence Status", callback=lambda _: rumps.notification("Trading OS", "Evidence", core.evidence_status())),
                              rumps.MenuItem("Pull Evidence", callback=lambda _: _run_bg(lambda: rumps.notification("Trading OS", "Pull", core.pull_evidence()))),
                              rumps.MenuItem("Open Latest Evidence", callback=lambda _: core.open_latest_evidence()),
                              rumps.MenuItem("Run Reconciliation", callback=lambda _: _run_bg(lambda: rumps.notification("Trading OS", "Reconcile", core.run_reconciliation())))]),
                ("Report Center", [rumps.MenuItem(k, callback=self._doc) for k in DOC]),
                ("Open File", [rumps.MenuItem(k, callback=self._file) for k in FILE]),
                None,
                rumps.MenuItem("Today", callback=self._today),
                rumps.MenuItem("Restart Dashboard ", callback=lambda _: _run_bg(core.restart_dashboard)),
                rumps.MenuItem("Quit", callback=rumps.quit_application),
            ]
            _run_bg(core.startup)
            self.timer = rumps.Timer(self._refresh, max(10, s["refresh_interval"]))
            self.timer.start()

        def _refresh(self, _):
            self.title = ICON.get(core.dashboard_health(), ICON["UNKNOWN"])

        def _bridge_status(self, _):
            rumps.notification("Trading OS — Bridge", "", core.bridge_status().replace("\n", " · ")[:200])

        def _quick(self, sender):
            out = core.run_quick(sender.title)
            rumps.notification("Trading OS", sender.title, out.strip().splitlines()[-1][:120] if out.strip() else "done")

        def _doc(self, sender):
            core.open_file(DOC[sender.title])

        def _file(self, sender):
            core.open_file(FILE[sender.title])

        def _today(self, _):
            rumps.notification("Trading OS — Today", "", " · ".join(core.today_actions())[:200])

    return TradingOS()


def main():
    try:
        app = build_menu_app()
        core.log("menu-bar app starting (rumps)")
        app.run()
    except ImportError:
        # graceful degradation: no rumps -> still one-click. Do startup, exit.
        core.log("rumps not installed -> launcher-only mode")
        print("Trading OS: rumps not installed -> running one-click startup "
              "(dashboard + tools). `pip3 install rumps` for the menu-bar icon.")
        r = core.startup()
        print(f"  dashboard: {r['dashboard']} | obsidian: {r['obsidian']} | "
              f"vscode: {r['vscode']} | git: {r['git'].get('branch')}@{r['git'].get('commit')}")
        sys.exit(0)


if __name__ == "__main__":
    main()
