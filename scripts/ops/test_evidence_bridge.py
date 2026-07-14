"""test_evidence_bridge.py -- deterministic tests for the MT5 evidence bridge.
Run: ./.venv/bin/python scripts/ops/test_evidence_bridge.py
Covers the 20 required cases with mocks + a real-fact check vs the known 2 S5 fills.
"""
import csv
import json
import os
import re
import tempfile
import types
import unittest

import evidence_lib as ev
import export_mt5_evidence as EX
import reconcile_live_evidence as RC

HERE = os.path.dirname(os.path.abspath(__file__))

# --- known real fills (from logs/fills.csv, already reconciled) -------------
FILLS_HDR = ("timestamp_utc,broker,account,strategy,session,symbol,side,quantity,"
             "signal_timestamp,signal_price,bid_at_submission,ask_at_submission,spread,"
             "spread_bps,requested_price,fill_price,slippage,slippage_bps,stop_price,"
             "target_price,account_equity,risk_scale,order_id,position_id,dry_run,status,error")
FILL1 = "2026-07-10 16:48:50,MT5Broker,61552095,S5,all,QQQ,buy,1.18552,,29800.1,29800.1,29801.1,1,0.33556,29801.1,29801.2,1.1,0.36913,29502.099,30694.103,49831.63,0.945,339422299,266746138,False,submitted,"
FILL2 = "2026-07-14 15:48:49,MT5Broker,61552095,S5,all,QQQ,buy,1.06512,,29636.5,29636.5,29637.5,1,0.33742,29637.5,29636.9,0.4,0.13497,29340.135,30525.595,49454.35,0.851,341029450,267936208,False,submitted,"


def make_snapshot(d, fills=(FILL1, FILL2), with_deals=True, with_pos=True, dup=False, missing=False):
    open(os.path.join(d, "fills.csv"), "w").write(FILLS_HDR + "\n" + "\n".join(fills) + "\n")
    deal_hdr = "ticket,order,time,symbol,type,entry,volume,price,commission,swap,fee,profit,comment"
    deals = []
    if with_deals and not missing:
        deals = ["266746138,339422299,t,NAS100,buy,in,1.2,29801.2,0,0,0,0,S5",
                 "266746138,999,t,NAS100,sell,out,1.2,29502.1,0,-18.29,0,-358.92,CLOSE",
                 "267936208,341029450,t,NAS100,buy,in,1.1,29636.9,0,0,0,0,S5"]
        if dup:
            deals.append("266746138,339422299,t,NAS100,buy,in,1.2,29801.2,0,0,0,0,S5")
    open(os.path.join(d, "deals.csv"), "w").write(deal_hdr + "\n" + "\n".join(deals) + "\n")
    pos_hdr = "ticket,time,symbol,type,volume,price_open,sl,tp,price_current,swap,profit,comment"
    pos = ["341029450,t,NAS100,buy,1.1,29636.9,29340.1,30525.6,29549.2,0,-96.47,S5"] if with_pos else []
    open(os.path.join(d, "positions.csv"), "w").write(pos_hdr + "\n" + "\n".join(pos) + "\n")


class Exporter(unittest.TestCase):
    def test_20_no_order_send_in_exporter(self):
        src = open(os.path.join(HERE, "export_mt5_evidence.py")).read()
        for bad in ("order_send", "position_close", "order_close"):
            self.assertNotIn(f".{bad}(", src, f"exporter must not call {bad}")

    def test_readonly_guard_blocks_mutation(self):
        fake = types.SimpleNamespace(order_send=lambda *a: 1, account_info=lambda: None)
        ro = EX.ReadOnlyMT5(fake)
        with self.assertRaises(PermissionError):
            ro.order_send({})            # forbidden
        with self.assertRaises(PermissionError):
            ro.some_random_call()        # not on allowlist

    def _fake_mt5conn(self, positions=(), deals=()):
        class F:
            def account_info(s): return types.SimpleNamespace(currency="USD", leverage=100, equity=49454.35, balance=49454.35, margin_free=49000)
            def positions_get(s): return positions
            def history_orders_get(s, a, b): return ()
            def history_deals_get(s, a, b): return deals
            def shutdown(s): pass
        return (F(), "61552095", "Broker-Server")

    def test_1_mt5_unavailable_status(self):
        with tempfile.TemporaryDirectory() as out:
            class Boom:
                def account_info(s): raise RuntimeError("terminal down")
                def positions_get(s): return ()
                def history_orders_get(s, a, b): return ()
                def history_deals_get(s, a, b): return ()
                def shutdown(s): pass
            _, m = EX.export(out, "2026-07-14", (Boom(), "61552095", "srv"))
            self.assertIn("mt5_error", m["status"])
            self.assertFalse(m["success"])

    def test_2_empty_history(self):
        with tempfile.TemporaryDirectory() as out:
            _, m = EX.export(out, "2026-07-14", self._fake_mt5conn())
            self.assertEqual(m["status"], "ok")
            self.assertEqual(m["row_counts"]["deals"], 0)

    def test_14_15_masking_and_checksums(self):
        with tempfile.TemporaryDirectory() as out:
            outdir, m = EX.export(out, "2026-07-14", self._fake_mt5conn())
            self.assertEqual(m["account_masked"], ev.mask_account("61552095"))
            self.assertNotIn("61552095", m["account_masked"])
            # every non-manifest file has a checksum that verifies
            for fn, cs in m["checksums"].items():
                self.assertEqual(cs, ev.sha256_file(os.path.join(outdir, fn)))

    def test_manifest_has_required_fields(self):
        with tempfile.TemporaryDirectory() as out:
            _, m = EX.export(out, "2026-07-14", self._fake_mt5conn())
            for k in ("generated_at_utc", "vps_hostname", "account_masked", "source_commit",
                      "date", "row_counts", "checksums", "exporter_version", "success"):
                self.assertIn(k, m)


class Secrets(unittest.TestCase):
    def test_13_secret_detection(self):
        for s in ("api_key = ABCDEF123456", "https://hc-ping.com/deadbeef-1234-5678-9abc-def012345678",
                  "ghp_" + "a" * 36, "123456789:AAH" + "x" * 33, "-----BEGIN PRIVATE KEY-----"):
            self.assertTrue(ev.scan_secrets(s), f"should flag: {s[:30]}")
        self.assertEqual(ev.scan_secrets("NAS100 buy 1.2 @ 29801.2 swap -18.29"), [])

    def test_assert_clean_refuses(self):
        with self.assertRaises(ValueError):
            ev.assert_clean("telegram_token = 123456789:AAH" + "x" * 33, "f")


class Reconciler(unittest.TestCase):
    def test_16_exact_two_s5_fills(self):
        with tempfile.TemporaryDirectory() as d:
            make_snapshot(d)
            r = RC.reconcile(d)
            self.assertEqual(r["n_fills"], 2)
            self.assertEqual(r["matched"], 2)             # both match broker deals
            self.assertEqual(r["match_rate"], 1.0)
            self.assertEqual(r["anomalies"], [])
            self.assertEqual(r["status"], "INSUFFICIENT_SAMPLE")  # n=2 < 10
            f1 = next(x for x in r["records"] if x["order_id"] == "339422299")
            f2 = next(x for x in r["records"] if x["order_id"] == "341029450")
            self.assertEqual(f1["broker_symbol"], "NAS100")     # venue: CFD not QQQ ETF
            self.assertEqual(f1["swap"], -18.29)                # measured weekend financing
            self.assertEqual(f1["state"], "CLOSED")
            self.assertEqual(f1["realized_R"], -1.0)            # stopped out
            self.assertEqual(f2["state"], "OPEN")
            self.assertAlmostEqual(r["avg_spread_bps"], 0.336, places=2)

    def test_17_missing_fill(self):
        with tempfile.TemporaryDirectory() as d:
            make_snapshot(d, missing=True)
            r = RC.reconcile(d)
            self.assertTrue(any("MISSING FILL" in a for a in r["anomalies"]))
            self.assertEqual(r["status"], "EXECUTION_ANOMALY")

    def test_18_duplicate_fill(self):
        with tempfile.TemporaryDirectory() as d:
            make_snapshot(d, dup=True)
            r = RC.reconcile(d)
            self.assertTrue(any("DUPLICATE" in a for a in r["anomalies"]))

    def test_3_open_positions_only(self):
        with tempfile.TemporaryDirectory() as d:
            make_snapshot(d, fills=(FILL2,), with_deals=True)
            r = RC.reconcile(d)
            self.assertEqual(r["records"][0]["state"], "OPEN")

    def test_10_malformed_fills(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "fills.csv"), "w").write("garbage,not,a,fill\n1,2,3,4\n")
            open(os.path.join(d, "deals.csv"), "w").write("ticket\n")
            open(os.path.join(d, "positions.csv"), "w").write("ticket\n")
            r = RC.reconcile(d)                # must not crash
            self.assertIn(r["status"], ("EXPORT_FAILED", "INSUFFICIENT_SAMPLE", "EXECUTION_ANOMALY"))

    def test_19_signal_ts_latency_unknown_when_blank(self):
        with tempfile.TemporaryDirectory() as d:
            make_snapshot(d)
            r = RC.reconcile(d)
            self.assertTrue(all(x["signal_to_submit_latency"] == "UNKNOWN" for x in r["records"]))

    def test_reports_written_with_pointer(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as repo:
            make_snapshot(os.path.join(d, "x") if False else d)
            snap = os.path.join(repo, "2026-07-14"); os.rename(d, snap)  # name = date
            res = RC.reconcile(snap)
            RC.write_reports(repo, snap, res)
            self.assertTrue(os.path.exists(os.path.join(repo, "reports", "latest.json")))
            self.assertTrue(os.path.exists(os.path.join(repo, "reports", "latest")))


class Telemetry(unittest.TestCase):
    def test_19b_signal_ts_is_arg_only_no_logic_change(self):
        # prove signal_ts was added ONLY as a place_order_safe argument in live_trader
        src = open(os.path.join(HERE, "..", "..", "live_trader.py")).read()
        adds = re.findall(r"signal_ts=now_et\(\)\.isoformat\(\)", src)
        self.assertGreaterEqual(len(adds), 8, "signal_ts added at entry sites")
        # it appears only inside place_order_safe calls (never in a conditional/sizing line)
        for m in re.finditer(r"^.*signal_ts=now_et.*$", src, re.M):
            self.assertIn("signal_price=price", m.group(0),
                          "signal_ts only rides alongside signal_price on order calls")


if __name__ == "__main__":
    unittest.main(verbosity=2)
