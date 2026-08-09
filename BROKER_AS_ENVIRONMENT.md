# THE BROKER IS PART OF THE EXPERIMENTAL ENVIRONMENT

Recorded 2026-08-05 after a correction from Colin.

## THE ERROR THIS DOCUMENT EXISTS TO PREVENT

The FTMO probe returned 166 symbols and **no bond class at all**. I wrote: *"the roadmap's #1
experiment is dead."*

That was wrong, and wrong in a specific, recurring way. Two claims were collapsed into one:

    A  "The breadth hypothesis cannot be EVALUATED on this broker."     <- what was measured
    B  "The breadth hypothesis is FALSE."                               <- what was written

A is an environmental limitation. B is a scientific conclusion. A never implies B.

Bonds are the diversifier that TSMOM, 7Twelve, Faber and every risk-parity result lean on. FTMO
not offering them says something about FTMO's product range. It says nothing whatsoever about
whether trend following across bonds would raise portfolio Sharpe.

## THE MEASURED ENVIRONMENTAL DIFFERENCE

Same strategy, same signal, two brokers, captured hours apart:

    FTMO-Demo 1514166963        166 symbols    0 bonds    swap mode POINTS
    Pepperstone-Demo 61552095  1729 symbols    7 bonds    swap mode INT_CURRENT

Ten times the universe, a whole asset class present instead of absent, and financing quoted in
a different unit with different semantics. These are not the same experimental environment, and
a result obtained in one does not automatically transfer to the other.

## CONSEQUENCE FOR EVERY VERDICT

Every strategy verdict in this project is now conditional on a broker. A verdict must state:

    - which broker and account the data came from
    - which asset classes were AVAILABLE, not merely which were tested
    - which hypotheses were NOT EVALUABLE there, listed explicitly

`BrokerProfile.capability_report()["limitations"]` emits the third item automatically, in
exactly the language above, so the distinction survives being copied into a summary.

## STATUS OF THE BREADTH HYPOTHESIS

    NOT EVALUABLE on FTMO           no bonds exist to test
    PARTIALLY EVALUATED on our 13-instrument daily panel (also bond-free):
        adding FX to a commodity/index trend book HALVED Sharpe (0.71 -> 0.37)
        because FX trend standalone measured -0.08
    UNTESTED                        whether adding BONDS raises Sharpe

The measured finding is narrow and stands: *breadth is not free — diversification only pays if
the added instruments carry the same signal edge.* It does NOT generalise to bonds, which have
a different economic driver (rates) from anything currently in the book.

To evaluate the bond leg we need either a broker that offers bond CFDs (Pepperstone does —
7 symbols) or a continuous futures panel. Both are recorded in DATA_ROADMAP.md.

## LONG-TERM DIRECTION

Strategies consume `BrokerProfile`, never MT5 directly. That makes them testable off-VPS,
comparable across brokers, and explicit about the environment they were validated in.

`scripts/broker_probe.py --any-account` profiles any connected broker; `broker_report.py
--compare` puts the captures side by side. The goal is a measured map of structural differences
across FTMO, Pepperstone, IC Markets, Interactive Brokers and any other venue — so that
"optimise for FTMO" is never silently confused with "optimise for markets".
