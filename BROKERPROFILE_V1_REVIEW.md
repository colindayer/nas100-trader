# BROKERPROFILE V1 — REVIEW AND CORRECTION PASS

    CAPTURE     FTMO Global Markets Ltd | FTMO-Demo | login 1514166963 | 20260810T125644Z
    SYMBOLS     166 (165 tradable)
    VERDICT     NEEDS_FIX  (minor, one field — see §8)

---

## 1. VERIFIED FTMO UNIVERSE

    class            n   tradable   >=1000 D1
    EQUITY          59         58          57     <- single-name CFDs. I said these did not exist.
    FX              43         43          43
    CRYPTO          30         30           7     <- 23 of 30 have little or no history
    EQUITY_INDEX    14         14          14
    METAL            9          9           9
    AGRICULTURAL     7          7           7
    ENERGY           4          4           4
    BOND             0          0           0     <- CONFIRMED ABSENT

    DXY.cash present (439 D1 bars) — a dollar-index macro proxy we did not know we had.

## 2. HISTORY DEPTH — tradable is NOT researchable

    can COMPUTE a 252-day signal      141
    can VALIDATE over 5 years         119
    can VALIDATE over 10 years         53

    class           min   median    max   >=10y  >=5y  >=252d
    FX              675     5742   6000      40    41      43   <- the only deep class
    METAL           431     2529   5701       7     8        9
    EQUITY           39     1454   5446       2    49       57
    EQUITY_INDEX    439     2192   2278       0    12       14   <- ZERO with 10 years
    ENERGY          427     1447   2657       1     2        4
    AGRICULTURAL    426      843    892       0     0        7   <- ZERO with 5 years
    CRYPTO            0        0   5508       3     7        7

**Only 53 of 166 symbols support a 10-year validation, and 40 of those are FX.** Every equity
index has under 10 years. Agriculturals cannot support even 5.

**MISSING FIELD:** `d1_from` / `d1_to` were lost with the failed capture and the metadata-only
recovery does not restore them. Bar counts are measured; first/last dates are not. This is the
single reason for the NEEDS_FIX verdict.

## 3. DATA QUALITY STATUS

    LIVE_AND_LONG_HISTORY    53     >=10y — full validation possible
    LIVE_LIMITED_HISTORY     66     >=5y
    LIVE_SIGNAL_ONLY         22     >=252d signal, NOT validatable on broker data
    METADATA_ONLY             4     tradable, not researchable
    UNAVAILABLE              21     listed, serves no data

**25 symbols (15%) are tradable but carry no usable history.** FTMO lists them; the feed
returns nothing. That is a real capability limit, not a probe defect — each cost 250-345s
inside one uninterruptible call before returning zero.

## 4. FINANCING — THE MOST IMPORTANT NUMBER IN THIS CAPTURE

Raw, per 1.0 lot per night, measured:

    leg     symbol        L $/night   S $/night   L annualised
    GOLD    XAUUSD           -93.35      -15.15        -32.93%
    SILVER  XAGUSD           -80.40       +1.80        -28.37%
    COPPER  XCUUSD           -17.51       +2.42         -6.18%
    NAS100  US100.cash        -6.51       +0.28         -2.30%
    OIL     UKOIL.cash        +2.19      -10.37         +0.77%
    SP500   US500.cash        -1.48       -0.14         -0.52%

Those are per FULL LOT, which the book never holds. Converted to the frozen portfolio's ACTUAL
average positions at a 5% volatility target, using its own measured weight path and its
measured long/short mix:

    leg      |w| mean   notional   lots    %long   $/night   annual drag
    GOLD        0.095      9,503  0.0219     67%    -1.481        -0.54%
    SILVER      0.053      5,251  0.0219     56%    -0.974        -0.36%
    OIL         0.046      4,554  0.6325     54%    -2.290        -0.84%
    COPPER      0.064      6,435  0.1430     51%    -1.107        -0.40%
    NAS100      0.081      8,140  0.3256     85%    -1.783        -0.65%
    SP500       0.103     10,304  1.7765     80%    -2.146        -0.78%
    ------------------------------------------------------------------
    TOTAL                                                         -3.57%

    frozen portfolio measured CAGR   +3.38%
    after financing                  -0.19%
    financing consumes                106% of gross return

**Financing has been absent from every backtest of the production strategy, and it is roughly
the size of the entire return.**

### CONFIDENCE IN THIS NUMBER — stated precisely

The swap values ARE measured. The conversion to lots requires `contract_size` and price, which
I supplied from standard conventions rather than reading the capture's own columns (the CSV is
on the VPS; I have only the printed summary). Sensitivity:

    XAUUSD / XAGUSD    contract 100 oz / 5000 oz are unambiguous industry standards -> HIGH
    US100 / US500      .cash CFDs at contract size 1 -> HIGH
    UKOIL.cash         contract could be 100 or 1000 -> drag could be 10x smaller or larger
    XCUUSD             contract size uncertain -> same risk

Taking ONLY the four high-confidence legs: **-2.33%/yr**, still 69% of gross return.

**The direction and order of magnitude are robust. The exact figure needs the CSV's own
contract_size and bid columns.** Do not treat -3.57% as final.

## 5. CORRECTION LEDGER — old claim, new evidence, corrected conclusion

**C1. "FTMO has no individual equities"**
- OLD: stated in ROADMAP.md and the OHLCV dataset entry; used to rule out PEAD and
  cross-sectional momentum as prop-irrelevant.
- EVIDENCE: 59 equity CFDs, 58 tradable, 57 with >=1000 D1 bars.
- CORRECTED: FTMO offers a substantial single-name universe. The claim came from the
  *Pepperstone* capture plus my assumption, never from FTMO measurement.

**C2. "PEAD is prop-irrelevant"**
- OLD: single-stock effect, no venue.
- EVIDENCE: the venue exists (59 names).
- CORRECTED: PEAD is venue-feasible and remains blocked on EARNINGS DATES, which we still do
  not have. The blocker moved, it did not disappear.

**C3. "Cross-sectional momentum is prop-irrelevant"**
- OLD: no universe.
- EVIDENCE: 57 equities with >=1000 D1 bars; 49 with >=5y.
- CORRECTED: now testable on FTMO. Caveat: this is a broker-curated list of ~59 large caps,
  NOT a point-in-time index. Survivorship is severe — these are the names FTMO offers TODAY.

**C4. "ContextSweepRetestV1 stage 6 is permanently data-limited"**
- OLD: only 3 of 7 Magnificent Seven, hourly only.
- EVIDENCE: AAPL MSFT NVDA AMZN META GOOG TSLA all present and tradable.
- CORRECTED: the CONSTITUENT gap is closed. The RESOLUTION gap is not — stage 6 needs
  synchronised M5, and only D1/H1 were measured. Downgrade from "permanently" to
  "blocked on an M5 capture".

**C5. "Magnificent Seven unavailable"**
- CORRECTED: all seven available. Stated wrongly on the basis of local ETF files.

**C6. "DXY unavailable"**
- OLD: listed as a missing macro variable.
- EVIDENCE: DXY.cash, 439 D1 bars, tradable.
- CORRECTED: available but LIVE_SIGNAL_ONLY (~1.7 years). Usable as a live conditioning
  variable; useless for multi-regime validation.

**C7. "Breadth expansion is capped by FTMO's symbol list"**
- CORRECTED: the list is not the cap. 141 symbols support a 252-day signal. The real cap is
  HISTORY: 53 with 10 years, and no bonds at all.

**C8. Rule 10a "breadth is not free" — UNCHANGED**
- Still stands. FX trend measured -0.08 standalone, and FX is 40 of the 53 deep-history
  symbols. The class with the best data is the class we measured as harmful.

## 6. RESEARCH OPPORTUNITIES UNLOCKED — listed, NOT run

    PEAD                        venue OK, still blocked on earnings dates
    cross-sectional momentum    57 names >=1000 D1; survivorship caveat is severe
    Mag7 breadth / leadership   all 7 present; needs an M5 capture for CSR stage 6
    DXY-conditioned signals     live-usable, 1.7y only
    equity dispersion           57 names, computable
    sector breadth              59 names is thin for sector work; US+EU mixed

**None of these change the prop objective on their own.** They widen what is testable; they do
not supply an edge, and the financing finding in §4 outranks all of them.

## 7. BROKER vs REFERENCE DATA — three distinct capabilities

    TRADE LIVE ON FTMO            165 symbols
    COMPUTE A 252d SIGNAL LIVE    141 symbols
    VALIDATE 5 YEARS on FTMO      119
    VALIDATE 10 YEARS on FTMO      53
    REQUIRES EXTERNAL REFERENCE   everything longer, and ALL bond research

Concrete instance: **COPPER is fully tradable with 431 D1 bars (~1.7 years).** It is a
production holding. Our backtest used 26 years of external reference data. FTMO cannot
reproduce that backtest for copper — the strategy is live-runnable and NOT re-validatable on
the venue's own data. Same for every AGRICULTURAL (max 892 bars) and every EQUITY_INDEX
(max 2278).

## 8. VERDICT — NEEDS_FIX

Not FREEZE_V1, for one specific reason: **section 2 requires first and last date per symbol,
and those fields are empty.** They were lost when the full capture died at ENOSPC, and the
metadata-only recovery cannot restore them. Everything else is complete and authoritative.

Two smaller items, neither blocking:
- 17 symbols classified with classifier confidence < 0.5 — need review before use
- 2 of 166 history depths missing (positions 161, 163 never printed to the log)

**The fix is cheap and targeted:** capture `d1_from`/`d1_to` for the 53 LIVE_AND_LONG_HISTORY
symbols only. Those are already warm, so it costs seconds and no meaningful disk. Everything
else stands as measured.

## PROVENANCE

    [MEASURED]  symbol list, classes, trade modes, swap, contract specs, spreads — FTMO 2026-08-10
    [MEASURED]  D1/H1 bar counts — FTMO 2026-08-09/10, recovered from the run log after ENOSPC
    [DERIVED]   financing drag at portfolio weights — measured swaps x measured weight path,
                but contract sizes for OIL and COPPER assumed, not read. See §4.
    [MISSING]   d1_from / d1_to
