"""test_btctrend_rebalance.py -- hedging-account-safe BTCTREND rebalance.
Bug fixed: on a hedging account, a plain opposite-side deal OPENED a stray short
(observed live: long 0.38 + short 0.05, both tagged BTCTREND, state file blind to it).
Run: python -m unittest test_btctrend_rebalance -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_emergency_protection import FakeMT5, _Obj, _pos

SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_trader.py")).read()


class FakeMT5Hedging(FakeMT5):
    """Extends the fake terminal: DEAL with position=<ticket> reduces/closes that ticket
    (hedging-correct); DEAL without position= opens a NEW position (the hedging trap)."""

    def order_send(self, req):
        self.sent.append(dict(req))
        if self.reject:
            return _Obj(retcode=10013, comment="invalid stops")
        if req["action"] == self.TRADE_ACTION_SLTP:
            for p in self.positions:
                if p.ticket == req["position"]:
                    p.sl = req["sl"]
        elif req["action"] == self.TRADE_ACTION_DEAL and "position" in req:
            for p in list(self.positions):
                if p.ticket == req["position"]:
                    p.volume = round(p.volume - req["volume"], 8)
                    if p.volume <= 1e-9:
                        self.positions.remove(p)
        elif req["action"] == self.TRADE_ACTION_DEAL:
            side = "long" if req["type"] == self.ORDER_TYPE_BUY else "short"
            newp = _pos(ticket=100 + len(self.positions), sl=req.get("sl", 0.0), side=side)
            newp.volume = req["volume"]; newp.comment = req.get("comment", "")
            self.positions.append(newp)
        return _Obj(retcode=self.TRADE_RETCODE_DONE, price=self.ask, order=42, deal=7)


def _tagged(ticket, vol, side="long", sl=0.0, comment="BTCTREND"):
    p = _pos(ticket=ticket, sl=sl, side=side)
    p.volume = vol; p.comment = comment
    return p


def _broker(m):
    from mt5_broker import MT5Broker
    b = MT5Broker.__new__(MT5Broker)
    b._mt5 = m
    b.SYMBOL_MAP = {"BTC": "BTCUSD"}
    b._ensure_connected = lambda: True
    return b


class NetQty(unittest.TestCase):
    def test_broker_truth_nets_long_and_short(self):
        # the exact live book: long 0.38 + short 0.05, both BTCTREND
        m = FakeMT5Hedging(positions=[_tagged(1, 0.38), _tagged(2, 0.05, "short")])
        self.assertAlmostEqual(_broker(m).net_qty("BTC", tag="BTCTREND"), 0.33)

    def test_tag_filter_excludes_sweep_positions(self):
        m = FakeMT5Hedging(positions=[_tagged(1, 0.38), _tagged(3, 0.10, comment="BTC")])
        self.assertAlmostEqual(_broker(m).net_qty("BTC", tag="BTCTREND"), 0.38)


class CloseInto(unittest.TestCase):
    def test_reduction_closes_into_long_never_opens_short(self):
        m = FakeMT5Hedging(positions=[_tagged(1, 0.38)])
        closed = _broker(m).close_into("BTC", 0.10, "long", tag="BTCTREND")
        self.assertAlmostEqual(closed, 0.10)
        self.assertAlmostEqual(m.positions[0].volume, 0.28)
        self.assertEqual(len(m.positions), 1)                  # no new position
        self.assertIn("position", m.sent[0])                   # ticket-targeted close

    def test_full_reduction_removes_position(self):
        m = FakeMT5Hedging(positions=[_tagged(1, 0.38)])
        closed = _broker(m).close_into("BTC", 0.38, "long", tag="BTCTREND")
        self.assertAlmostEqual(closed, 0.38)
        self.assertEqual(m.positions, [])

    def test_buy_delta_first_closes_stray_short(self):
        # self-healing of the live stray-short book
        m = FakeMT5Hedging(positions=[_tagged(1, 0.38), _tagged(2, 0.05, "short")])
        closed = _broker(m).close_into("BTC", 0.05, "short", tag="BTCTREND")
        self.assertAlmostEqual(closed, 0.05)
        self.assertEqual([p.ticket for p in m.positions], [1])  # short leg gone

    def test_reduce_spans_multiple_tickets(self):
        m = FakeMT5Hedging(positions=[_tagged(1, 0.10), _tagged(2, 0.10)])
        closed = _broker(m).close_into("BTC", 0.15, "long", tag="BTCTREND")
        self.assertAlmostEqual(closed, 0.15)
        self.assertAlmostEqual(sum(p.volume for p in m.positions), 0.05)

    def test_never_closes_more_than_held(self):
        m = FakeMT5Hedging(positions=[_tagged(1, 0.10)])
        closed = _broker(m).close_into("BTC", 0.50, "long", tag="BTCTREND")
        self.assertAlmostEqual(closed, 0.10)                    # capped at holdings
        self.assertEqual(m.positions, [])


class WiringLocks(unittest.TestCase):
    def test_broker_is_source_of_truth(self):
        self.assertIn('net_qty("BTC", tag="BTCTREND")', SRC)
        self.assertIn("state drift", SRC)                       # divergence logged

    def test_sell_path_never_plain_opposite_deal_on_mt5(self):
        seg = SRC[SRC.index("def run_btc_trend"):SRC.index("SWEEP_BASKET")]
        self.assertIn('close_into("BTC", rest, "long"', seg)    # reductions close into longs
        self.assertIn("NOT opening a short", seg)               # long/flat invariant kept

    def test_buy_path_closes_ALL_shorts_verifies_then_buys_with_sl(self):
        seg = SRC[SRC.index("def run_btc_trend"):SRC.index("SWEEP_BASKET")]
        self.assertIn('close_into("BTC", None, "short"', seg)   # ALL shorts, not delta-capped
        self.assertIn("ABORTING buy", seg)                      # verify-then-abort
        self.assertLess(seg.index('close_into("BTC", None, "short"'),
                        seg.index('sl=emergency_floor'))        # flatten first, then protected buy

    def test_donchian_signal_still_untouched(self):
        self.assertIn('H = close.rolling(20).max().shift(1); L = close.rolling(10).min().shift(1)', SRC)
        self.assertIn('BTC_TREND_VOLTARGET = 0.20', SRC)




class NeverHedgeInvariant(unittest.TestCase):
    """Investigation 2026-07-20: the mission's required scenarios. BTCTREND must never
    hold simultaneous long+short exposure, on hedge OR netting semantics."""

    def _b(self, m):
        return _broker(m)

    def test_close_all_mode_closes_entire_short_side(self):
        # D-A regression: delta smaller than the short must still flatten ALL shorts
        m = FakeMT5Hedging(positions=[_tagged(1, 0.05, "short"), _tagged(2, 0.02, "short")])
        closed = self._b(m).close_into("BTC", None, "short", tag="BTCTREND")
        self.assertAlmostEqual(closed, 0.07)
        self.assertEqual(m.positions, [])

    def test_ticket_registry_matches_rewritten_comment(self):
        # D-C / RT5 regression: broker rewrote the comment -> ticket registry still owns it
        p = _tagged(9, 0.03, "short", comment="to #342163006")   # rewritten
        m = FakeMT5Hedging(positions=[p])
        closed = self._b(m).close_into("BTC", None, "short", tag="BTCTREND", tickets=[9])
        self.assertAlmostEqual(closed, 0.03)

    def test_foreign_positions_never_touched(self):
        # safety: other strategies / manual trades (different comment, not in registry)
        m = FakeMT5Hedging(positions=[_tagged(5, 0.10, "short", comment="BTC"),
                                      _tagged(6, 0.10, "short", comment="")])
        closed = self._b(m).close_into("BTC", None, "short", tag="BTCTREND", tickets=[])
        self.assertEqual(closed, 0.0)
        self.assertEqual(len(m.positions), 2)

    def test_close_failure_leaves_position_and_reports_zero(self):
        m = FakeMT5Hedging(positions=[_tagged(1, 0.05, "short")], reject=True)
        closed = self._b(m).close_into("BTC", None, "short", tag="BTCTREND")
        self.assertEqual(closed, 0.0)                    # honest: nothing closed
        self.assertEqual(len(m.positions), 1)            # caller must abort the buy

    def test_partial_close_artifact_covered_next_run(self):
        # partial fill leaves 0.02; a second (retry/daily) run flattens the remainder
        m = FakeMT5Hedging(positions=[_tagged(1, 0.05, "short")])
        b = self._b(m)
        b.close_into("BTC", 0.03, "long" if False else "short", tag="BTCTREND")  # partial
        self.assertAlmostEqual(m.positions[0].volume, 0.02)
        b.close_into("BTC", None, "short", tag="BTCTREND")                        # rerun
        self.assertEqual(m.positions, [])

    def test_long_reduction_never_opens_short(self):
        # reversal path: reducing 0.05 from a 0.03 long closes 0.03 and STOPS
        m = FakeMT5Hedging(positions=[_tagged(1, 0.03)])
        closed = self._b(m).close_into("BTC", 0.05, "long", tag="BTCTREND")
        self.assertAlmostEqual(closed, 0.03)
        self.assertEqual(m.positions, [])                # flat; no short ever created

    def test_repeated_daily_runs_idempotent(self):
        m = FakeMT5Hedging(positions=[_tagged(1, 0.04), _tagged(2, 0.01, "short")])
        b = self._b(m)
        b.close_into("BTC", None, "short", tag="BTCTREND")
        b.close_into("BTC", None, "short", tag="BTCTREND")   # duplicate execution
        longs = [p for p in m.positions if p.type == FakeMT5.POSITION_TYPE_BUY]
        shorts = [p for p in m.positions if p.type == FakeMT5.POSITION_TYPE_SELL]
        self.assertEqual(len(shorts), 0)
        self.assertEqual(len(longs), 1)                  # longs untouched

    def test_netting_semantics_also_safe(self):
        # on a netting account the same ticket-targeted close reduces the single position
        m = FakeMT5Hedging(positions=[_tagged(1, 0.05, "short")])
        self._b(m).close_into("BTC", None, "short", tag="BTCTREND")
        self.assertEqual(m.positions, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
