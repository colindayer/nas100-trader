"""build_knowledge_graph.py -- emit knowledge_graph.json (nodes+edges) from the
known OS map. Documentation only; reads nothing from production, writes one JSON.
Edge types: validated_by, reviewed_by, superseded_by, contradicts, depends_on,
feeds, documents, shadowed_by."""
import json, os
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def N(id, type, **kw): return dict(id=id, type=type, **kw)
nodes = [
  # strategies
  N("S1","strategy",name="Asian Sweep",validation="YES",production="LIVE"),
  N("S2","strategy",name="Gold FVG",validation="FIXED",production="LIVE",clock="restarted 2026-07-14"),
  N("S3","strategy",name="Abnormal Volume",validation="PARTIAL",production="LIVE"),
  N("S4","strategy",name="Multi-Sweep",validation="YES",production="LIVE"),
  N("S5","strategy",name="ORB",validation="PARTIAL-CFD",production="LIVE"),
  N("OVN","strategy",name="Overnight Drift",validation="YES",production="LIVE"),
  N("BTC","strategy",name="BTC Sweep",validation="PARTIAL",production="LIVE"),
  N("BTCTREND","strategy",name="BTC Trend / XSMOM",validation="YES",production="LIVE-off-funded"),
  # experiments
  N("EXP_universe","experiment",file="research/experiments/part_a_universe.py"),
  N("EXP_macro","experiment",file="research/experiments/part_b_macro_regimes.py"),
  N("EXP_tsmom","experiment",file="research/experiments/part_c_tsmom.py"),
  N("EXP_vixts","experiment",file="research/experiments/vix_ts_gate_test.py"),
  N("EXP_atr","experiment",file="research/experiments/atr_compression_review.py"),
  N("EXP_weekend","experiment",file="research/experiments/weekend_exposure_test.py"),
  N("EXP_reentry","experiment",file="S5 re-entry replay (docs/S5_REENTRY_REVIEW.md)"),
  N("EXP_dix","experiment",file="research/archive/EXP-20260710-01-dix-regime-filter-on-3-pillars.md",status="rejected"),
  # reviews / audits
  N("REV_parity","review",file="docs/LIVE_TRADING_PARITY.md"),
  N("REV_valaudit","review",file="docs/STRATEGY_VALIDATION_AUDIT.md"),
  N("REV_weekend","review",file="docs/WEEKEND_EXPOSURE_AUDIT.md"),
  N("REV_s3","review",file="docs/S3_VALIDATION_REVIEW.md"),
  N("REV_reentry","review",file="docs/S5_REENTRY_REVIEW.md"),
  N("REV_drift","review",file="docs/LIVE_RESEARCH_DRIFT.md"),
  N("REV_shadow","review",file="docs/ETF_FORWARD_SHADOW_REVIEW.md"),
  N("REV_vixts","review",file="research/results/vix_ts_gate_REVIEW.md"),
  N("REV_atr","review",file="research/results/atr_compression_REVIEW.md"),
  N("REV_ovn","review",file="docs/OVERNIGHT_MOMENTUM_REVIEW.md"),
  N("REV_macrofilter","review",file="docs/MACRO_FILTER_REVIEW.md"),
  N("REV_graveyard","review",file="docs/RESEARCH_GRAVEYARD_AUDIT.md"),
  # ideas
  N("IDEA_dix","idea",file="research/ideas/2026-07-10-dark-pool-dix-regime-filter.md",status="rejected"),
  N("IDEA_vixts","idea",file="research/ideas/2026-07-11-vix-term-structure-regime-gate.md",status="shadow"),
  N("IDEA_intraday","idea",file="research/ideas/2026-07-12-intraday-return-momentum-decomposition.md",status="rejected"),
  # findings
  N("FIND_s2inert","finding",note="S2 hourly-FVG structurally inert (0/75d)"),
  N("FIND_s3drift","finding",note="S3 live rule = strict subset ~4/yr vs 15/yr"),
  N("FIND_cfdfin","finding",note="CFD financing ~3bps/day kills slow/monthly holds"),
  N("FIND_weekend","finding",note="S5 benefits from weekend holds; S3 harmed"),
  N("FIND_reentry","finding",note="S5 same-day re-entry breakeven, accepted"),
  # reports / governance
  N("RPT_month1","report",file="docs/MONTH_1_LIVE_REPORT.md"),
  N("RPT_committee","report",file="docs/MONTHLY_EVIDENCE_COMMITTEE.md"),
  N("RPT_readiness","report",file="docs/PROP_READINESS.md"),
  N("RPT_ledger","report",file="docs/EVIDENCE_LEDGER.md"),
  N("RPT_clockreset","report",file="docs/CLOCK_RESETS.md"),
  N("RPT_backlog","report",file="docs/RESEARCH_BACKLOG.md"),
  N("RPT_monitor","report",file="docs/NEXT_30_DAY_MONITORING_PLAN.md"),
  N("RPT_vpsfix","report",file="docs/VPS_UPDATE_FIX.md"),
  # dashboard pages
  *[N(f"DASH_{p}","dashboard_page",name=p) for p in
    ["HOME","STRATEGIES","SHADOW","RESEARCH","GRAVEYARD","EXECUTION","EVIDENCE","LOGS","SETTINGS"]],
  # obsidian notes
  *[N(f"OBS_{s}","obsidian_note",file=f"vault/03-Validated-Strategies/{f}")
    for s,f in [("S1","S1 Asian Sweep.md"),("S2","S2 Gold FVG.md"),("S3","S3 Abnormal Volume.md"),
                ("S4","S4 Multi Sweep.md"),("S5","S5 ORB.md"),("OVN","Overnight Drift.md"),
                ("BTC","BTC Sweep.md"),("BTCTREND","BTC Trend.md")]],
]
def E(s,t,r): return dict(source=s,target=t,rel=r)
edges = [
  # validated_by
  E("S1","REV_parity","validated_by"), E("S4","REV_parity","validated_by"),
  E("S2","FIND_s2inert","validated_by"), E("S5","REV_reentry","validated_by"),
  # reviewed_by
  *[E(s,"REV_valaudit","reviewed_by") for s in ["S1","S2","S3","S4","S5","BTC"]],
  E("S3","REV_s3","reviewed_by"), E("S5","REV_drift","reviewed_by"),
  *[E(s,"REV_weekend","reviewed_by") for s in ["S1","S3","S5"]],
  E("OVN","REV_ovn","reviewed_by"),
  # superseded_by (S2 hourly -> daily; ideas -> experiments)
  E("FIND_s2inert","S2","superseded_by"),
  E("IDEA_vixts","EXP_vixts","superseded_by"),
  # contradicts (validation audit contradicts prior parity 'all green')
  E("REV_valaudit","REV_parity","contradicts"),
  E("FIND_weekend","S3","contradicts"),
  # depends_on
  E("S3","S3","depends_on"), E("BTC","S1","depends_on"),
  E("S4","S1","depends_on"), E("EXP_reentry","S5","depends_on"),
  E("RPT_month1","RPT_ledger","depends_on"),
  # feeds (experiments/findings feed reports)
  E("EXP_weekend","REV_weekend","feeds"), E("REV_weekend","FIND_weekend","feeds"),
  E("EXP_reentry","REV_reentry","feeds"), E("REV_reentry","FIND_reentry","feeds"),
  E("EXP_universe","REV_shadow","feeds"), E("EXP_vixts","REV_vixts","feeds"),
  E("EXP_atr","REV_atr","feeds"), E("EXP_tsmom","REV_graveyard","feeds"),
  E("FIND_s3drift","REV_valaudit","feeds"), E("REV_valaudit","RPT_committee","feeds"),
  E("REV_shadow","RPT_month1","feeds"), E("RPT_clockreset","RPT_monitor","feeds"),
  # documents
  *[E(f"OBS_{s}",s,"documents") for s in ["S1","S2","S3","S4","S5","OVN","BTC","BTCTREND"]],
  E("DASH_STRATEGIES","S1","documents"), E("DASH_GRAVEYARD","REV_graveyard","documents"),
  E("DASH_EVIDENCE","RPT_committee","documents"), E("DASH_SHADOW","REV_shadow","documents"),
  E("KG","S1","documents"),
  # shadowed_by
  E("S1","REV_shadow","shadowed_by"), E("S5","REV_shadow","shadowed_by"),
  E("S5","IDEA_vixts","shadowed_by"),
  # rejected alternatives (contradicts strategy edge)
  E("EXP_dix","S1","contradicts"), E("IDEA_intraday","BTCTREND","contradicts"),
  E("EXP_atr","S5","contradicts"),
]
nodes.append(N("KG","report",file="docs/KNOWLEDGE_GRAPH.md"))
graph = dict(generated="2026-07-13", note="Documentation only. Nodes/edges over the trading OS.",
             node_count=len(nodes), edge_count=len(edges), nodes=nodes, edges=edges)
out = os.path.join(REPO, "knowledge_graph.json")
json.dump(graph, open(out,"w"), indent=2)
# validate: every edge endpoint exists
ids = {n["id"] for n in nodes}
bad = [e for e in edges if e["source"] not in ids or e["target"] not in ids]
assert not bad, f"dangling edges: {bad}"
print(f"wrote knowledge_graph.json: {len(nodes)} nodes, {len(edges)} edges, 0 dangling")
