"""BOT_I — Asian liquidity sweep -> London reversal. A HYPOTHESIS, running in shadow.

Seven conditions must hold in order. Each is measured and recorded, so when the Brain has
enough observations it can say WHICH of them carries the edge -- or that none does.

    sweep -> rejection -> displacement -> structure break -> origin -> retest -> rejection

DETERMINISM
  Every condition is evaluated on CLOSED bars only, strictly before `now`. Swing points use a
  fixed fractal definition and are never revised once formed. Run this at 09:14 and again at
  16:00 and the same session yields the same answer -- a discretionary pattern that repaints
  cannot be evidence about anything.

WHY SHADOW FIRST
  Seven sequential conditions is a lot of ways to be subtly wrong, and a state machine that
  looks right in code can still fire on the wrong bar. Shadow mode records the full signal and
  every measurement without risking capital, so the first question answered is "does this fire
  when it should" -- not "does it make money".

STAGED EXITS
  TP1/TP2/TP3 are computed and RECORDED, but the live target is TP2. Partial closes need
  position-management machinery the desk does not have, and inventing it before knowing
  whether the entry works would be building on an unproven premise. The record will show which
  stage each trade reached.
"""
from __future__ import annotations

from bot_base import Bot, Signal


class AsianSweepLondonReversal(Bot):
    playbook = "SWEEP"
    primary = {"TRANSITION", "AT_HTF_LEVEL"}
    secondary = {"RANGE", "EXTENDED", "WEAK_TREND"}
    avoids = {"STRONG_TREND"}          # a sweep that keeps going is a breakout, not a reversal
    strategy_id = "BOT_I_asia_sweep_london_reversal"
    strategy_version = "1.0.0"
    symbol = "XAUUSD"
    stage = "SHADOW"
    shadow = True                      # NEVER sends an order until explicitly promoted
    prior_expectancy_R, prior_n = 0.00, 10
    risk_override = 0.0005

    # ---- session definition (London clock)
    ASIA_START_H, ASIA_END_H = 0, 7
    LONDON_START_H, EXIT_H, EXIT_M = 7, 16, 0

    # ---- objective thresholds. Recorded on every signal so they can be re-derived later.
    MIN_SWEEP_ATR = 0.05               # must genuinely pierce, not graze
    MAX_ACCEPT_BARS = 20               # rejection must be prompt; acceptance outside invalidates
    DISP_BODY_ATR = 0.12               # impulse body vs D1 ATR
    DISP_BODY_PCT = 0.60               # body must dominate the bar, not be a wick
    SWING_FRACTAL = 2                  # bars each side; fixed, so swings never repaint
    ORIGIN_REJECT_WICK = 0.45          # ONE deterministic rejection rule at the origin
    STOP_BUFFER_ATR = 0.10

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _swings(d, n):
        """Deterministic fractals on closed bars. A swing at i needs n higher/lower bars on
        BOTH sides, so it is only ever confirmed n bars later and never revised."""
        h, l = d["high"].to_numpy(), d["low"].to_numpy()
        highs, lows = [], []
        for i in range(n, len(d) - n):
            if all(h[i] > h[i - k] and h[i] > h[i + k] for k in range(1, n + 1)):
                highs.append((i, float(h[i])))
            if all(l[i] < l[i - k] and l[i] < l[i + k] for k in range(1, n + 1)):
                lows.append((i, float(l[i])))
        return highs, lows

    def generate_signal(self, ctx) -> Signal | None:
        import pandas as pd
        now, st, bars = ctx["now_london"], ctx.get("state") or {}, ctx["m1"]
        if bars is None or len(bars) < 120:
            return self._no("insufficient M1 history")
        atr = st.get("atr20_d1")
        if not atr:
            return self._no("no D1 ATR -- every threshold here is ATR-relative")

        day = now.normalize()
        lon_open = day + pd.Timedelta(hours=self.LONDON_START_H)
        cut = day + pd.Timedelta(hours=self.EXIT_H, minutes=self.EXIT_M)
        if now < lon_open:
            return self._no(f"before London: {now:%H:%M} < {self.LONDON_START_H:02d}:00")
        if now >= cut:
            return self._no(f"after session close {self.EXIT_H:02d}:{self.EXIT_M:02d}")
        if ctx.get("traded_today", {}).get(self.strategy_id):
            return self._no("already traded today")

        closed = bars[bars.index < now]          # CLOSED bars only -- no repainting
        asia = closed[(closed.index >= day + pd.Timedelta(hours=self.ASIA_START_H)) &
                      (closed.index < day + pd.Timedelta(hours=self.ASIA_END_H))]
        if len(asia) < 60:
            return self._no(f"Asia range has {len(asia)} bars, need 60")
        a_hi, a_lo = float(asia["high"].max()), float(asia["low"].min())
        a_range = a_hi - a_lo
        if a_range <= 0:
            return self._no("degenerate Asia range")

        lon = closed[closed.index >= lon_open]
        if len(lon) < 10:
            return self._no(f"London has {len(lon)} closed bars, need 10")

        h, l = lon["high"].to_numpy(), lon["low"].to_numpy()
        o, c = lon["open"].to_numpy(), lon["close"].to_numpy()

        # ---- 1. SWEEP: which side got taken, and by how much
        up_pierce = (h.max() - a_hi) / atr
        dn_pierce = (a_lo - l.min()) / atr
        if max(up_pierce, dn_pierce) < self.MIN_SWEEP_ATR:
            return self._no(f"no sweep: {up_pierce:+.3f}/{dn_pierce:+.3f} ATR beyond Asia, "
                            f"need {self.MIN_SWEEP_ATR}")
        side = -1 if up_pierce >= dn_pierce else 1        # sweep high -> look for shorts
        sweep_i = int(h.argmax() if side < 0 else l.argmin())
        sweep_px = float(h[sweep_i] if side < 0 else l[sweep_i])
        sweep_atr = up_pierce if side < 0 else dn_pierce

        # ---- 2. REJECTION: back inside the range, promptly. Acceptance invalidates.
        after = range(sweep_i + 1, len(lon))
        rej_i = next((i for i in after
                      if (c[i] < a_hi if side < 0 else c[i] > a_lo)), None)
        if rej_i is None:
            return self._no(f"swept {sweep_atr:.2f} ATR but never closed back inside Asia")
        if rej_i - sweep_i > self.MAX_ACCEPT_BARS:
            return self._no(f"acceptance outside the range: {rej_i - sweep_i} bars to reject, "
                            f"max {self.MAX_ACCEPT_BARS} -- this is a breakout, not a sweep")
        rejection_speed = rej_i - sweep_i

        # ---- 3. DISPLACEMENT: an abnormal impulse, not merely a candle of the right colour
        disp_i = None
        for i in range(rej_i, len(lon)):
            body = abs(c[i] - o[i])
            rng = h[i] - l[i]
            right_way = (c[i] < o[i]) if side < 0 else (c[i] > o[i])
            if (right_way and body >= self.DISP_BODY_ATR * atr
                    and rng > 0 and body / rng >= self.DISP_BODY_PCT):
                disp_i = i
                break
        if disp_i is None:
            return self._no(f"rejected at bar {rej_i} but no displacement "
                            f"(need body >= {self.DISP_BODY_ATR} ATR and "
                            f"{self.DISP_BODY_PCT:.0%} of range)")
        disp_body = abs(c[disp_i] - o[disp_i])
        disp_atr = disp_body / atr

        # ---- 4. STRUCTURE SHIFT: a swing formed BEFORE the impulse must break
        pre = lon.iloc[:disp_i + 1]
        sw_hi, sw_lo = self._swings(pre, self.SWING_FRACTAL)
        if side < 0:
            if not sw_lo:
                return self._no("no confirmed swing low to break")
            ref_i, ref_px = sw_lo[-1]
            broke = c[disp_i:].min() < ref_px
        else:
            if not sw_hi:
                return self._no("no confirmed swing high to break")
            ref_i, ref_px = sw_hi[-1]
            broke = c[disp_i:].max() > ref_px
        if not broke:
            return self._no(f"displacement at {disp_i} did not break the "
                            f"{'low' if side < 0 else 'high'} at {ref_px:.2f}")
        mss_dist_atr = abs(ref_px - sweep_px) / atr

        # ---- 5. ORIGIN: last opposite-colour candle before the impulse
        org_i = None
        for i in range(disp_i - 1, max(disp_i - 30, -1), -1):
            if (c[i] > o[i]) if side < 0 else (c[i] < o[i]):
                org_i = i
                break
        if org_i is None:
            return self._no("no displacement origin candle found before the impulse")
        org_hi, org_lo = float(h[org_i]), float(l[org_i])

        # ---- 6. RETEST: price must come BACK into the origin. No chasing.
        bid, ask = ctx["bid"], ctx["ask"]
        px = ask if side > 0 else bid
        if not (org_lo <= px <= org_hi):
            return self._no(f"no retest: {px:.2f} outside origin "
                            f"[{org_lo:.2f}, {org_hi:.2f}]")
        retrace_depth = (abs(px - c[disp_i]) / disp_body) if disp_body else None

        # ---- 7. REJECTION AT ORIGIN: one deterministic rule, the wick
        last = len(lon) - 1
        rng_l = h[last] - l[last]
        wick = ((h[last] - max(o[last], c[last])) if side < 0
                else (min(o[last], c[last]) - l[last]))
        wick_ratio = (wick / rng_l) if rng_l > 0 else 0.0
        if wick_ratio < self.ORIGIN_REJECT_WICK:
            return self._no(f"no rejection at origin: wick {wick_ratio:.0%} of bar, "
                            f"need {self.ORIGIN_REJECT_WICK:.0%}")

        # ---- execution. Stop is STRUCTURE, never a fixed distance.
        stop = sweep_px + side * -1 * self.STOP_BUFFER_ATR * atr
        stop = sweep_px + (self.STOP_BUFFER_ATR * atr if side < 0
                           else -self.STOP_BUFFER_ATR * atr)
        risk = abs(px - stop)
        if risk <= 0:
            return self._no("degenerate stop")
        tp2 = a_lo if side < 0 else a_hi                       # opposite side of Asia
        internal = (min((v for _, v in sw_lo), default=None) if side < 0
                    else max((v for _, v in sw_hi), default=None))
        tp1 = internal if internal is not None else px + side * risk
        tp3 = st.get("lvl_prev_day_low" if side < 0 else "lvl_prev_day_high")

        return Signal(
            self.strategy_id, self.strategy_version, now.isoformat(), self.symbol,
            side, "market", px, stop, tp2,
            int((cut - now).total_seconds() // 60),
            ["asia_sweep_london_reversal",
             f"sweep={sweep_atr:.2f}atr", f"disp={disp_atr:.2f}atr",
             f"mss={ref_px:.2f}", f"origin=[{org_lo:.2f},{org_hi:.2f}]"],
            {
                # the seven conditions, each measured
                "asia_high": a_hi, "asia_low": a_lo, "asia_range": a_range,
                "sweep_price": sweep_px, "sweep_size_atr": sweep_atr,
                "rejection_speed_bars": rejection_speed,
                "displacement_size_atr": disp_atr, "displacement_body": disp_body,
                "structure_break_level": ref_px, "structure_break_dist_atr": mss_dist_atr,
                "origin_high": org_hi, "origin_low": org_lo,
                "retracement_depth": retrace_depth,
                "origin_wick_ratio": wick_ratio,
                "entry_delay_bars": last - sweep_i,
                # staged targets: recorded, TP2 is live
                "tp1_internal": tp1, "tp2_asia_opposite": tp2, "tp3_htf": tp3,
                # shared fields the desk's machinery expects
                "sl_dist": risk, "pre_range": a_range, "spread": ask - bid,
                "minutes_since_entry": 0,
            })
