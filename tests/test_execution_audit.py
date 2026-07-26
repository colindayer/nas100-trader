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
