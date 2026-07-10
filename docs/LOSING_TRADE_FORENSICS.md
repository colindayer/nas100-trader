# LOSING TRADE FORENSICS — live vs research, trade by trade

_Investigation only; nothing implemented. Evidence sources: MT5 terminal snapshots
(2026-07-06 19:45 ET and 2026-07-07 01:08 ET), risk-state files, local logs,
LIVE_TRADE_REVIEW.md, session records. Fields the Mac cannot see (VPS-only MT5
history, Actions cloud logs) are marked UNKNOWN — with the exact command to
retrieve them listed in §5._

## 0. The complete losing-trade ledger

Only TWO live losing trades exist to date:

| # | Venue | Instrument | Loss | Status |
|---|---|---|---|---|
| **L1** | Alpaca paper | QQQ (OVN overnight) | **≈ −$1,567 realized** (equity 100,000.00 → 98,432.63) | flattened manually ~2026-07-02 |
| **L2** | MT5 Pepperstone demo | NAS100 (S5 ORB), ticket 335431483 | **−136.63 floating** at last snapshot | final close UNKNOWN (VPS history) |

Non-losers, for completeness: XAUUSD cluster 06-29/30 (+0.28 total), NAS100
ticket 335622424 (+16.00 floating — see §4, unattributable), BTCUSD min-lot
bracket test (deliberate). **Correction to the record:** LIVE_TRADE_REVIEW.md
called the Alpaca equity decline "pre-existing account history." The numbers say
otherwise: peak 100,000.00 → July month-start 98,432.63 ≈ the QQQ flatten loss,
and the position provably existed (it was closed via `DELETE /v2/positions/QQQ`).
Fable's review only saw Mac-local logs; the buys came from **GitHub Actions cloud
runs whose logs never touch this machine.** L1 is ours.

---

## 1. Trade report — L1 (Alpaca QQQ, OVN, ≈ −$1,567)

| Field | Value | Source / note |
|---|---|---|
| signal timestamp | Mon/Tue 15:00–16:00 ET window, ~2026-06-29/30 (cloud runs) | OVN design + incident record |
| expected entry | 33 shares (equity × 25% / price) — ONE entry | `run_overnight` sizing |
| actual broker entry | **134 shares** accumulated across repeated cloud runs | incident record (over-buy) |
| spread | ~1c on QQQ (negligible) | liquid ETF |
| slippage | UNKNOWN (Actions logs ephemeral) | — |
| stop distance | **NONE — naked** (pre-fix era) | no broker SL existed |
| TP distance | none (OVN is a time-exit strategy) | by design |
| regime filters | VIX/regime not gating OVN entry (calendar strategy) | by design |
| session filter | entry window respected; **EXIT window missed** (15:30–16:00 too narrow; crash-era runs died before exit logic) | incident record |
| volatility filter | n/a for OVN | — |
| sizing | **4.06× intended** (134 vs 33) — state file does not persist on ephemeral Actions runners → every run re-bought | root-cause record |
| execution latency | UNKNOWN | — |

**FIRST divergence point: at ENTRY — position sizing.** The cloud runner lost
`ovn_state.json` between runs and re-bought until the position was ~4× design
size (~100% of equity vs 25%). Second divergence: the next-morning exit never
executed (window miss + the emoji-crash era killing scheduled runs). Third: no
broker-side stop existed to cap any of it.

**Research counterfactual:** backtest OVN = 33 shares, one night, exit at open.
The same price path on design size ≈ **−$390**. Divergence cost ≈ **−$1,180**
(oversize) plus multi-day exposure the research never takes.

## 2. Trade report — L2 (MT5 NAS100, S5 ORB, ticket 335431483)

| Field | Value | Source / note |
|---|---|---|
| signal timestamp | 2026-07-06 17:48:45 server (UTC+3) = **10:48 ET Monday** — S5 window (10–13 ET), scheduler's :49 firing | MT5 snapshot |
| expected entry | close of a COMPLETED hourly breakout bar > ORB-high | backtest `run_intraday` (signal on bar i−1, entry at bar i) |
| actual broker entry | **29789.6 mid-forming 10:00 bar** at 10:48 | MT5 snapshot; parity gap #4 |
| spread | UNKNOWN exactly (NAS100 CFD typically ~1–2 index pts ≈ 0.3–0.7 bps) | Pepperstone spec |
| slippage vs signal | UNKNOWN — the signal-bar price was never logged | **the measurement gap (§6)** |
| stop distance | **NONE at entry — naked era** (SL/TP fix landed 07-07); design = −1% (29491.7) | LIVE_SAFETY history |
| TP distance | design +3% (30683.3) — not attached | naked era |
| regime filters | VIX 21d = 18.0 (<20 ✓), spy_bull = True ✓ | log REGIME line 07-06 |
| session filter | 10–13 ET window ✓ | timestamp |
| volatility filter | vol_ok (>0.6× ORB volume) presumed ✓ — fired; UNKNOWN raw values (VPS log) | — |
| sizing | 1.3 lots = 50,000 × 0.0075 / (29789.6 × 0.010) = 1.26 → 1.3 (volume_step) — **CORRECT, matches S5 exactly** | reconstruction above |
| execution latency | seconds-scale (hourly poll → market order); fine for hourly system | design |
| swap cost | position held overnight: NAS100 long swap ≈ −7.3/lot/night ≈ 2.4 bps/night — **research assumes 0** | Pepperstone swap col |

**FIRST divergence point: at ENTRY PRICE — mid-forming-bar fill.** The research
enters on a completed bar's close; live bought at whatever the price was at :48.
Price then faded to ~29684 (−0.35%): within the −1% stop envelope, so **the
backtest would still be in this trade** — the floating −136 is not (yet)
divergence-caused. The real divergences are (a) an entry price the research never
sees, unmeasured; (b) no bracket for 12+ hours (risk, unrealized); (c) overnight
swap drag the research doesn't model.

---

## 3. Every observed divergence, ranked by expected PnL impact

| Rank | Divergence | Evidence | Realized / expected impact | Status |
|---|---|---|---|---|
| 1 | **Bot-managed exits fail while positions are naked** (crash era + window miss) | L1 | **−$1,567 realized — 100% of realized live losses** | ✅ FIXED (brackets, catastrophe stop, excepthook) |
| 2 | **State-loss oversizing on ephemeral runners** (re-buys: 134 vs 33) | L1 | ≈ −$1,180 of #1's loss | ✅ FIXED (`open_syms` position check) |
| 3 | **Mid-forming-bar entry vs closed-bar research** | L2 entry 29789.6 @ :48 | unmeasured; est ±5–15 bps *per fill*, recurring on every S1/S4/S5 trade | ❌ OPEN & UNMEASURED |
| 4 | **CFD swap + spread vs the 3 bps ETF cost model** | L2 swap −7.3/lot/night ≈ 2.4 bps/night; spread ~0.5 bps | recurring drag on every MT5 hold; compounds on multi-day positions | ❌ OPEN & UNMEASURED |
| 5 | **Unattributable order** (ticket 335622424 — §4) | no strategy/session matches | +16 this time; process risk unbounded if manual trading mixes with the bot | ⚠️ needs explanation |
| 6 | Naked-entry window on MT5 (07-06→07) | L2 | risk only — price never approached the design stop; no realized excess | ✅ FIXED |

## 4. Integrity flag — the order nobody placed

Ticket **335622424**: BUY 1.0 lot NAS100 @ 29668.5, 2026-07-07 02:00:14 server
= **19:00 ET** — outside every strategy's session window, and 1.0 lots matches
**no sizing formula** (S5→1.26, S1→0.79, S4→0.45, OVN→0.42). Most likely a
manual terminal order or a min-lot test. If it was manual: manual trades in the
bot's account contaminate the 30-day statistics. It must be identified and
tagged (MT5 history shows the comment field — the bot stamps `S1/S5/OVN/TEST`;
a blank comment = manual).

## 5. UNKNOWNs and how to close them (evidence commands, VPS)

```
MT5 -> Toolbox -> History (or):  python fetch_mt5_history.py     # deals w/ comments
type logs\mt5_all.log | findstr "07-06"                          # S5 signal line + ORB values
schtasks /query /tn Nas100Bot-MT5 /v | findstr "Last"            # run timing vs :48 fill
```
These close: L2's exact signal values, final L2 close price/PnL, and ticket
335622424's comment (attribution).

## 6. THE single highest-impact fix (recommendation only — nothing implemented)

The top two realized-loss divergences (#1, #2) are already fixed. Of what
remains, #3 and #4 share one root: **the system never records what the research
would have paid.** No signal-bar price, no spread, no swap is captured at fill
time — so the live-vs-backtest cost gap is invisible, and the month-end go/no-go
would compare live PnL against research costs nobody has verified.

**Recommended fix: a fill ledger — at every order, log (a) the signal bar's
close (the research's assumed entry), (b) the actual fill price, (c) current
spread, (d) computed slippage in bps, appended to one `logs/fills.csv`.**
One logging addition at the `place_order_safe` boundary; zero strategy logic
touched. It converts the two open divergences from *unmeasured* to *measured*,
feeds the monitoring plan's slippage checklist item (currently impossible to
perform — the data doesn't exist), and arms the month-end decision with real
execution costs. Everything else on the open list is either already fixed,
awaiting VPS evidence (§5), or too small to outrank measurement itself.
