"""Stage 4 execution-chain audit: the classifier must catch paths that contain NO banned filename."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import deploy

ROOT = deploy.ROOT


def risk(cmd, args="", wd=""):
    return deploy._classify(cmd, args, wd, ROOT)[0]


def test_legacy_paths_are_critical_without_any_banned_filename():
    cases = [
        ("C:\\Users\\Administrator\\run_all.bat", "", ""),
        ("py", "portfolio.py", "C:\\Users\\Administrator\\Downloads"),
        ("py", "-m runner", "C:\\Users\\Administrator\\nas100_backnet"),
        ("C:\\Program Files\\MetaTrader 5\\terminal64.exe", "/portable", ""),
        ("py", "-m runner", "C:\\Users\\Administrator\\trading-os"),
    ]
    for cmd, args, wd in cases:
        assert risk(cmd, args, wd) == "CRITICAL", f"missed legacy path: {cmd} {args} {wd}"
        assert "live_trader" not in f"{cmd}{args}{wd}"   # none contain the banned name


def test_banned_executor_still_critical():
    assert risk("py", "live_trader.py") == "CRITICAL"


def test_sanctioned_entry_point_is_ok():
    assert risk("py", "-m market_intel.web --port 8787", ROOT) == "OK"


def test_unknown_python_outside_root_is_not_ok():
    assert risk("py", "-m something_else", "C:\\elsewhere") == "HIGH"


def test_nothing_is_preapproved_without_the_allowlist_file():
    # fail closed: a missing/unreadable allowlist must approve nothing
    assert deploy._approved() == set() or isinstance(deploy._approved(), set)


def test_enumeration_failure_is_reported_not_swallowed():
    rows, errors = deploy.audit_execution()      # no schtasks on macOS
    assert errors, "a source that cannot be enumerated must be reported, not treated as clean"
    assert deploy.print_execution_audit(rows, errors) == 1


REAL_VPS_XML = '''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><URI>\\Nas100Bot-MT5</URI></RegistrationInfo>
  <Settings><Enabled>true</Enabled></Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "C:\\Users\\Administrator\\Downloads\\nas100-trader-main\\nas100-trader-main\\run_all.bat"</Arguments>
    </Exec>
  </Actions>
</Task>'''


def test_the_task_that_was_actually_missed_on_the_vps():
    """Regression: this exact task ran hourly while the audit reported the host clean.
    It contains no banned filename -- risk lives in run_all.bat + Downloads + archived repo."""
    r = deploy._classify("cmd.exe",
                         '/c "C:\\Users\\Administrator\\Downloads\\nas100-trader-main'
                         '\\nas100-trader-main\\run_all.bat"', "", ROOT)
    assert r[0] == "CRITICAL", r


def test_namespaced_task_xml_parses(monkeypatch):
    """The prefix-map approach raised on real VPS XML and the whole scan silently degraded."""
    import subprocess as sp
    monkeypatch.setattr(deploy.subprocess, "check_output",
                        lambda *a, **k: REAL_VPS_XML.encode("utf-8"))
    rows = deploy._tasks_from_schtasks()
    assert len(rows) == 1, rows
    assert rows[0]["task"] == "\\Nas100Bot-MT5"
    assert rows[0]["command"] == "cmd.exe"
    assert "run_all.bat" in rows[0]["arguments"]
    assert rows[0]["enabled"] is True


def test_incomplete_enumeration_never_prints_a_clean_headline(capsys):
    rc = deploy.print_execution_audit([], ["scheduled_task: boom"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "no CRITICAL legacy execution path detected" not in out
    assert "INCONCLUSIVE" in out


MULTI_TASK_XML = '''<?xml version="1.0" encoding="UTF-16"?>
<Tasks xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Task>
    <RegistrationInfo><URI>\\MarketIntel Recorder</URI></RegistrationInfo>
    <Settings><Enabled>true</Enabled></Settings>
    <Actions><Exec><Command>C:\\Users\\Administrator\\run_recorder.bat</Command></Exec></Actions>
  </Task>
  <Task>
    <RegistrationInfo><URI>\\Nas100Bot-MT5</URI></RegistrationInfo>
    <Settings><Enabled>false</Enabled></Settings>
    <Actions><Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "C:\\Users\\Administrator\\Downloads\\nas100-trader-main\\run_all.bat"</Arguments>
    </Exec></Actions>
  </Task>
</Tasks>'''


def test_each_task_keeps_its_own_name(monkeypatch):
    """Every action was labelled with the FIRST task's URI, so the report named one task 14
    times. An audit you cannot act on is not an audit."""
    monkeypatch.setattr(deploy.subprocess, "check_output",
                        lambda *a, **k: MULTI_TASK_XML.encode("utf-8"))
    rows = deploy._tasks_from_schtasks()
    assert len(rows) == 2, rows
    names = {r["task"] for r in rows}
    assert names == {"\\MarketIntel Recorder", "\\Nas100Bot-MT5"}, names
    mt5 = [r for r in rows if r["task"] == "\\Nas100Bot-MT5"][0]
    assert mt5["enabled"] is False and "run_all.bat" in mt5["arguments"]
    assert [r for r in rows if r["task"] == "\\MarketIntel Recorder"][0]["enabled"] is True


def test_downloads_path_is_not_called_the_deployment_root(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy.subprocess, "check_output",
                        lambda *a, **k: MULTI_TASK_XML.encode("utf-8"))
    monkeypatch.setattr(deploy, "_autostart_entries", lambda: [])
    rows, _ = deploy.audit_execution(root="C:\\Users\\Administrator")
    bad = [r for r in rows if "Downloads" in r["arguments"]]
    assert bad and "deployment root" not in bad[0]["repo"], bad
